from fastapi import APIRouter, Depends, Request, Response

from openpype.api import ResponseFactory
from openpype.api.dependencies import (
    dep_current_user,
    dep_folder_id,
    dep_project_name,
    dep_thumbnail_content_type,
    dep_version_id,
)
from openpype.entities.folder import FolderEntity
from openpype.entities.user import UserEntity
from openpype.entities.version import VersionEntity
from openpype.exceptions import RecordNotFoundException
from openpype.lib.postgres import Postgres

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


async def store_thumbnail(project_name: str, entity_id: str, mime: str, payload: bytes):
    query = f"""
        INSERT INTO project_{project_name}.thumbnails (id, mime, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (id)
        DO UPDATE SET data = EXCLUDED.data
    """
    await Postgres.execute(query, entity_id, mime, payload)


async def retrieve_thumbnail(project_name: str, entity_id: str) -> Response:
    query = f"SELECT mime, data FROM project_{project_name}.thumbnails WHERE id = $1"
    async for record in Postgres.iterate(query, entity_id):
        return Response(
            media_type=record["mime"], status_code=200, content=record["data"]
        )
    raise RecordNotFoundException("Thumbnail does not exist")


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
    payload = await request.body()
    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_write_access(user)

    await store_thumbnail(
        project_name=project_name,
        entity_id=folder_id,
        mime=content_type,
        payload=payload,
    )
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
    return await retrieve_thumbnail(project_name, folder_id)


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
    folder = await VersionEntity.load(project_name, version_id)
    await folder.ensure_write_access(user)

    await store_thumbnail(
        project_name=project_name,
        entity_id=version_id,
        mime=content_type,
        payload=payload,
    )
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
    return await retrieve_thumbnail(project_name, version_id)
