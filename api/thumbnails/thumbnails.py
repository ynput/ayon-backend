import functools

from fastapi import APIRouter, Query, Request, Response

from ayon_server.api.dependencies import (
    AllowGuests,
    AllowProjectSkeleton,
    CurrentUser,
    FolderID,
    NoTraces,
    ProjectName,
    TaskID,
    ThumbnailContentType,
    ThumbnailID,
    VersionID,
    WorkfileID,
)
from ayon_server.entities.folder import FolderEntity
from ayon_server.entities.task import TaskEntity
from ayon_server.entities.version import VersionEntity
from ayon_server.entities.workfile import WorkfileEntity
from ayon_server.exceptions import (
    ForbiddenException,
    NotFoundException,
)
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_info
from ayon_server.helpers.thumbnails import (
    PlaceholderOption,
    get_fake_thumbnail,
    resolve_thumbnail,
    store_project_skeleton_thumbnail,
    store_thumbnail,
)
from ayon_server.helpers.thumbnails.invalidate_thumbnail import AffectedEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID

#
# Router
#

router = APIRouter(tags=["Thumbnails"])


async def body_from_request(request: Request) -> bytes:
    result = b""
    async for chunk in request.stream():
        result += chunk
    logger.debug(f"Received thumbnail payload of {len(result)} bytes")
    return result


@functools.cache
def get_fake_thumbnail_response() -> Response:
    """Generate a "fake thumbnail" response.

    This function creates a FastAPI Response object containing an
    1x1 transparent png and appropriate headers.
    """
    response = Response(status_code=203, content=get_fake_thumbnail())
    response.headers["Content-Type"] = "image/png"
    response.headers["Cache-Control"] = "max-age=3600"
    return response


async def retrieve_thumbnail(
    project_name: str,
    thumbnail_id: str | None,
    placeholder: PlaceholderOption = "none",
    original: bool = False,
) -> Response:
    query = f"SELECT * FROM project_{project_name}.thumbnails WHERE id = $1"
    if thumbnail_id is not None:
        try:
            res = await Postgres.fetch(query, thumbnail_id)
        except Postgres.UndefinedTableError:
            pass  # project does not exist
        else:
            if res:
                payload = None
                if original:
                    storage = await Storages.project(project_name)
                    try:
                        payload = await storage.get_thumbnail(thumbnail_id)
                    except FileNotFoundError:
                        pass

                record = res[0]
                payload = payload or record["data"]
                return Response(
                    media_type=record["mime"],
                    status_code=200,
                    content=payload,
                    headers={
                        "X-Thumbnail-Id": thumbnail_id,
                        "X-Thumbnail-Time": str(record.get("created_at", 0)),
                        "Cache-Control": "max-age=3600",
                    },
                )

    if placeholder == "empty":
        return get_fake_thumbnail_response()

    raise NotFoundException("Thumbnail not found")


#
# Direct thumbnail access
#


class CreateThumbnailResponseModel(OPModel):
    id: str = Field(..., title="Thumbnail ID", example="a1f2b3c4d5e6f7g8h9i0")
    affected_entities: list[AffectedEntity] | None = None


@router.post("/projects/{project_name}/thumbnails")
async def create_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    """Create a thumbnail.

    This endpoint is used to create a thumbnail not associated with any entity.
    Returns the ID of the created thumbnail. which can be used to assign it to
    an entity.
    """
    thumbnail_id = EntityID.create()
    payload = await body_from_request(request)
    affected_entities = await store_thumbnail(
        project_name,
        thumbnail_id,
        payload,
        mime=content_type,
        user_name=user.name,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.put(
    "/projects/{project_name}/thumbnails/{thumbnail_id}",
)
async def update_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    thumbnail_id: ThumbnailID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    """Create or update a thumbnail with a specific ID.

    This endpoint is used to create or update a thumbnail by its ID.
    Since this is can be an security issue, this endpoint is only available
    to users with the `manager` role or higher.
    """

    if not user.is_manager:  # TBD
        raise ForbiddenException("Only managers can update arbitrary thumbnails")
    payload = await body_from_request(request)
    affected_entities = await store_thumbnail(
        project_name,
        thumbnail_id,
        payload,
        mime=content_type,
        user_name=user.name,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.get(
    "/projects/{project_name}/thumbnails/{thumbnail_id}",
    response_class=Response,
    dependencies=[NoTraces],
)
async def get_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    thumbnail_id: ThumbnailID,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    """Get a thumbnail by its ID.

    This endpoint is used to retrieve a thumbnail by its ID.
    Since this is can be an security issue, this endpoint is only available
    to users with the `manager` role or higher.
    """
    if not user.is_manager:  # TBD
        raise ForbiddenException("Only managers can access arbitrary thumbnails")

    return await retrieve_thumbnail(
        project_name, thumbnail_id, placeholder=placeholder, original=original
    )


#
# Folder endpoints
#


@router.post("/projects/{project_name}/folders/{folder_id}/thumbnail")
async def create_folder_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    """Create a new thumbnail for a folder.

    Returns a thumbnail ID, which is also saved into the entity
    database record.
    """

    payload = await body_from_request(request)
    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_update_access(user, thumbnail_only=True)

    thumbnail_id = EntityID.create()
    affected_entities = await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        mime=content_type,
        payload=payload,
        user_name=user.name,
        entity=folder,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.get(
    "/projects/{project_name}/folders/{folder_id}/thumbnail",
    dependencies=[NoTraces, AllowGuests],
)
async def get_folder_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    return await resolve_thumbnail(
        project_name,
        "folder",
        folder_id,
        user=user,
        placeholder=placeholder,
        original=original,
    )


#
# Versions endpoints
#


@router.post("/projects/{project_name}/versions/{version_id}/thumbnail")
async def create_version_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await body_from_request(request)
    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_update_access(user)

    thumbnail_id = EntityID.create()
    affected_entities = await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        payload=payload,
        mime=content_type,
        user_name=user.name,
        entity=version,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.get(
    "/projects/{project_name}/versions/{version_id}/thumbnail",
    dependencies=[NoTraces, AllowGuests],
)
async def get_version_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    return await resolve_thumbnail(
        project_name,
        "version",
        version_id,
        user=user,
        placeholder=placeholder,
        original=original,
    )


#
# Workfile endpoints
#


@router.post("/projects/{project_name}/workfiles/{workfile_id}/thumbnail")
async def create_workfile_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await body_from_request(request)
    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_update_access(user)

    thumbnail_id = EntityID.create()
    affected_entities = await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        payload=payload,
        mime=content_type,
        user_name=user.name,
        entity=workfile,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.get(
    "/projects/{project_name}/workfiles/{workfile_id}/thumbnail",
    dependencies=[NoTraces, AllowGuests],
)
async def get_workfile_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    return await resolve_thumbnail(
        project_name,
        "workfile",
        workfile_id,
        user=user,
        placeholder=placeholder,
        original=original,
    )


#
# Task endpoints
#


@router.post("/projects/{project_name}/tasks/{task_id}/thumbnail")
async def create_task_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await body_from_request(request)
    task = await TaskEntity.load(project_name, task_id)
    await task.ensure_update_access(user)
    thumbnail_id = EntityID.create()
    affected_entities = await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        payload=payload,
        mime=content_type,
        user_name=user.name,
        entity=task,
    )
    return CreateThumbnailResponseModel(
        id=thumbnail_id,
        affected_entities=affected_entities,
    )


@router.get(
    "/projects/{project_name}/tasks/{task_id}/thumbnail",
    dependencies=[NoTraces, AllowGuests],
)
async def get_task_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    return await resolve_thumbnail(
        project_name,
        "task",
        task_id,
        user=user,
        placeholder=placeholder,
        original=original,
    )


#
# Project thumbnail
#

PROJECT_THUMBNAIL_ID = "0" * 32  # reserved thumbnail ID for project thumbnail


@router.post(
    "/projects/{project_name}/thumbnail",
    dependencies=[AllowProjectSkeleton],
)
async def create_project_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await body_from_request(request)

    user.check_permissions("project.anatomy", project_name, write=True)

    project_info = await get_project_info(project_name, with_skeleton=True)
    if project_info.skeleton:
        await store_project_skeleton_thumbnail(
            project_name,
            payload,
            mime=content_type,
            user_name=user.name,
        )
        return CreateThumbnailResponseModel(id=PROJECT_THUMBNAIL_ID)

    await store_thumbnail(
        project_name=project_name,
        thumbnail_id=PROJECT_THUMBNAIL_ID,
        payload=payload,
        mime=content_type,
        user_name=user.name,
    )

    # bump project updated_at to trigger client cache invalidation, since project
    # does not have thumbnailHash yet
    await Postgres.execute(
        """
        UPDATE public.projects
        SET updated_at = NOW() WHERE name = $1
        """,
        project_name,
    )
    return CreateThumbnailResponseModel(id=PROJECT_THUMBNAIL_ID)


@router.get(
    "/projects/{project_name}/thumbnail",
    dependencies=[NoTraces, AllowGuests, AllowProjectSkeleton],
)
async def get_project_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    placeholder: PlaceholderOption = Query("empty"),
    original: bool = Query(False),
) -> Response:
    project_info = await get_project_info(project_name, with_skeleton=True)

    await user.ensure_project_access(project_name)

    if project_info.skeleton:
        query = """
            SELECT * FROM public.project_skeleton_thumbnails
            WHERE project_name = $1
        """
        res = await Postgres.fetch(query, project_name)
        if res:
            record = res[0]
            payload = record["data"]
            return Response(
                media_type=record["mime"],
                status_code=200,
                content=payload,
                headers={
                    "X-Thumbnail-Time": str(record.get("created_at", 0)),
                    "Cache-Control": f"max-age={60}",
                },
            )

        if placeholder == "empty":
            return get_fake_thumbnail_response()
        else:
            raise NotFoundException("Project thumbnail not found")

    return await retrieve_thumbnail(
        project_name,
        PROJECT_THUMBNAIL_ID,
        placeholder=placeholder,
        original=original,
    )
