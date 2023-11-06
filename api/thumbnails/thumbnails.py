import base64

from fastapi import APIRouter, Request, Response

from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
    ProjectName,
    ThumbnailContentType,
    ThumbnailID,
    VersionID,
    WorkfileID,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities.folder import FolderEntity
from ayon_server.entities.version import VersionEntity
from ayon_server.entities.workfile import WorkfileEntity
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID

#
# Router
#

router = APIRouter(
    tags=["Thumbnails"],
)

#
# Common


def get_fake_thumbnail():
    base64_string = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="  # noqa
    response = Response(status_code=203)
    response.content = base64.b64decode(base64_string)
    response.headers["Content-Type"] = "image/png"
    response.headers["Cache-Control"] = f"max-age={3600*24}"
    return response


async def store_thumbnail(
    project_name: str,
    thumbnail_id: str,
    mime: str,
    payload: bytes,
):
    if len(payload) < 10:
        raise BadRequestException("Thumbnail cannot be empty")

    query = f"""
        INSERT INTO project_{project_name}.thumbnails (id, mime, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (id)
        DO UPDATE SET data = EXCLUDED.data
        RETURNING id
    """
    await Postgres.execute(query, thumbnail_id, mime, payload)
    for entity_type in ["workfiles", "versions", "folders"]:
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                conn.execute(
                    f"""
                    UPDATE project_{project_name}.{entity_type}
                    SET updated_at = NOW() WHERE thumbnail_id = $1
                    """,
                    thumbnail_id,
                )


async def retrieve_thumbnail(project_name: str, thumbnail_id: str | None) -> Response:
    query = f"SELECT * FROM project_{project_name}.thumbnails WHERE id = $1"
    if thumbnail_id is not None:
        async for record in Postgres.iterate(query, thumbnail_id):
            return Response(
                media_type=record["mime"],
                status_code=200,
                content=record["data"],
                headers={
                    "X-Thumbnail-Id": thumbnail_id,
                    "X-Thumbnail-Time": str(record.get("created_at", 0)),
                    "Cache-Control": f"max-age={3600*24}",
                },
            )
    return get_fake_thumbnail()


#
# Direct thumbnail access
#


class CreateThumbnailResponseModel(OPModel):
    id: str = Field(..., title="Thumbnail ID", example="a1f2b3c4d5e6f7g8h9i0")


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
    payload = await request.body()
    await store_thumbnail(project_name, thumbnail_id, content_type, payload)
    return CreateThumbnailResponseModel(id=thumbnail_id)


@router.put(
    "/projects/{project_name}/thumbnails/{thumbnail_id}",
    status_code=204,
)
async def update_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    thumbnail_id: ThumbnailID,
    content_type: ThumbnailContentType,
) -> EmptyResponse:
    """Create or update a thumbnail with a specific ID.

    This endpoint is used to create or update a thumbnail by its ID.
    Since this is can be an security issue, this endpoint is only available
    to users with the `manager` role or higher.
    """

    if not user.is_manager:
        raise ForbiddenException("Only managers can update arbitrary thumbnails")
    payload = await request.body()
    await store_thumbnail(project_name, thumbnail_id, content_type, payload)
    return EmptyResponse()


@router.get(
    "/projects/{project_name}/thumbnails/{thumbnail_id}",
    response_class=Response,
)
async def get_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    thumbnail_id: ThumbnailID,
) -> Response:
    """Get a thumbnail by its ID.

    This endpoint is used to retrieve a thumbnail by its ID.
    Since this is can be an security issue, this endpoint is only available
    to users with the `manager` role or higher.
    """
    if not user.is_manager:
        raise ForbiddenException("Only managers can access arbitrary thumbnails")

    return await retrieve_thumbnail(project_name, thumbnail_id)


#
# Folder endpoints
#


@router.post("/projects/{project_name}/folders/{folder_id}/thumbnail", status_code=201)
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
    payload = await request.body()
    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_update_access(user)

    thumbnail_id = EntityID.create()
    await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        mime=content_type,
        payload=payload,
    )
    folder.thumbnail_id = thumbnail_id
    await folder.save()
    return CreateThumbnailResponseModel(id=thumbnail_id)


@router.get("/projects/{project_name}/folders/{folder_id}/thumbnail")
async def get_folder_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
) -> Response:
    try:
        folder = await FolderEntity.load(project_name, folder_id)
        await folder.ensure_read_access(user)
    except AyonException:
        return get_fake_thumbnail()
    return await retrieve_thumbnail(project_name, folder.thumbnail_id)


#
# Versions endpoints
#


@router.post(
    "/projects/{project_name}/versions/{version_id}/thumbnail", status_code=201
)
async def create_version_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await request.body()
    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_update_access(user)

    thumbnail_id = EntityID.create()
    await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        mime=content_type,
        payload=payload,
    )
    version.thumbnail_id = thumbnail_id
    await version.save()
    return CreateThumbnailResponseModel(id=thumbnail_id)


@router.get("/projects/{project_name}/versions/{version_id}/thumbnail")
async def get_version_thumbnail(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> Response:
    try:
        version = await VersionEntity.load(project_name, version_id)
        await version.ensure_read_access(user)
    except AyonException:
        return get_fake_thumbnail()
    return await retrieve_thumbnail(project_name, version.thumbnail_id)


#
# Workfile endpoints
#


@router.post(
    "/projects/{project_name}/workfiles/{workfile_id}/thumbnail", status_code=201
)
async def create_workfile_thumbnail(
    request: Request,
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    content_type: ThumbnailContentType,
) -> CreateThumbnailResponseModel:
    payload = await request.body()
    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_update_access(user)

    thumbnail_id = EntityID.create()
    await store_thumbnail(
        project_name=project_name,
        thumbnail_id=thumbnail_id,
        mime=content_type,
        payload=payload,
    )
    workfile.thumbnail_id = thumbnail_id
    await workfile.save()
    return CreateThumbnailResponseModel(id=thumbnail_id)


@router.get(
    "/projects/{project_name}/workfiles/{workfile_id}/thumbnail",
)
async def get_workfile_thumbnail(
    user: CurrentUser, project_name: ProjectName, workfile_id: WorkfileID
) -> Response:
    try:
        workfile = await WorkfileEntity.load(project_name, workfile_id)
        await workfile.ensure_read_access(user)
    except AyonException:
        return get_fake_thumbnail()
    return await retrieve_thumbnail(project_name, workfile.thumbnail_id)
