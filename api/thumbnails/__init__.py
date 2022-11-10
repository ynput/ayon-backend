from fastapi import APIRouter, Depends, Request, Response

from openpype.api import ResponseFactory
from openpype.api.dependencies import (
    dep_current_user,
    dep_folder_id,
    dep_project_name,
    dep_thumbnail_content_type,
    dep_thumbnail_id,
    dep_version_id,
    dep_workfile_id,
)
from openpype.entities.folder import FolderEntity
from openpype.entities.user import UserEntity
from openpype.entities.version import VersionEntity
from openpype.entities.workfile import WorkfileEntity
from openpype.exceptions import BadRequestException, ForbiddenException
from openpype.lib.postgres import Postgres
from openpype.types import OPModel
from openpype.utils import EntityID

#
# Router
#

router = APIRouter(
    tags=["Thumbnails"],
)

#
# Common
#

responses = {
    401: ResponseFactory.error(401),
    403: ResponseFactory.error(403),
    404: ResponseFactory.error(404),
}


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


async def retrieve_thumbnail(project_name: str, thumbnail_id: str | None) -> Response:
    query = f"SELECT mime, data FROM project_{project_name}.thumbnails WHERE id = $1"
    if thumbnail_id is not None:
        async for record in Postgres.iterate(query, thumbnail_id):
            return Response(
                media_type=record["mime"], status_code=200, content=record["data"]
            )
    return Response(status_code=204)


#
# Direct thumbnail access
#


class CreateThumbnailResponseModel(OPModel):
    id: str


@router.post(
    "/projects/{project_name}/thumbnails",
    response_model=CreateThumbnailResponseModel,
    responses=responses,
)
async def create_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    content_type: str = Depends(dep_thumbnail_content_type),
):
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
    responses=responses,
    response_class=Response,
)
async def update_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    thumbnail_id: str = Depends(dep_thumbnail_id),
    content_type: str = Depends(dep_thumbnail_content_type),
):
    """Create or update a thumbnail with a specific ID.

    This endpoint is used to create or update a thumbnail by its ID.
    Since this is can be an security issue, this endpoint is only available
    to users with the `manager` role or higher.
    """

    if not user.is_manager:
        raise ForbiddenException("Only managers can update arbitrary thumbnails")
    payload = await request.body()
    await store_thumbnail(project_name, thumbnail_id, content_type, payload)
    return Response(status_code=204)


@router.get(
    "/projects/{project_name}/thumbnails/{thumbnail_id}",
    response_class=Response,
    responses=responses,
)
async def get_thumbnail(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    thumbnail_id: str = Depends(dep_thumbnail_id),
):
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


@router.post(
    "/projects/{project_name}/folders/{folder_id}/thumbnail",
    status_code=201,
    response_class=Response,
    responses=responses,
)
async def create_folder_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
    content_type: str = Depends(dep_thumbnail_content_type),
):
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
    return Response(status_code=201)


@router.get(
    "/projects/{project_name}/folders/{folder_id}/thumbnail",
    response_class=Response,
    responses=responses,
)
async def get_folder_thumbnail(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_read_access(user)
    return await retrieve_thumbnail(project_name, folder.thumbnail_id)


#
# Versions endpoints
#


@router.post(
    "/projects/{project_name}/versions/{version_id}/thumbnail",
    status_code=201,
    response_class=Response,
    responses=responses,
)
async def create_version_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
    content_type: str = Depends(dep_thumbnail_content_type),
):
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
    return Response(status_code=201)


@router.get(
    "/projects/{project_name}/versions/{version_id}/thumbnail",
    response_class=Response,
    responses=responses,
)
async def get_version_thumbnail(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
):
    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_read_access(user)
    return await retrieve_thumbnail(project_name, version.thumbnail_id)


#
# Workfile endpoints
#


@router.post(
    "/projects/{project_name}/workfiles/{workfile_id}/thumbnail",
    status_code=201,
    response_class=Response,
    responses=responses,
)
async def create_workfile_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    workfile_id: str = Depends(dep_workfile_id),
    content_type: str = Depends(dep_thumbnail_content_type),
):
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
    return Response(status_code=201)


@router.get(
    "/projects/{project_name}/workfiles/{workfile_id}/thumbnail",
    response_class=Response,
    responses=responses,
)
async def get_workfile_thumbnail(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    workfile_id: str = Depends(dep_workfile_id),
):
    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_read_access(user)
    return await retrieve_thumbnail(project_name, workfile.thumbnail_id)
