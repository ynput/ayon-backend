from fastapi import APIRouter, Depends, Header, Request, Response

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user, dep_folder_id, dep_project_name
from openpype.entities.folder import FolderEntity
from openpype.entities.user import UserEntity
from openpype.exceptions import RecordNotFoundException, UnsupportedMediaException
from openpype.lib.postgres import Postgres


#
# Router
#

router = APIRouter(
    tags=["Thumbnails"],
)


@router.post(
    "/projects/{project_name}/folders/{folder_id}/thumbnail",
    status_code=201,
    response_class=Response,
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
        404: ResponseFactory.error(404),
    },
)
async def create_folder_thumbnail(
    request: Request,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
    content_type: str = Header(...),
):
    if content_type not in ["image/png", "image/jpeg"]:
        raise UnsupportedMediaException("Thumbnail must be in png or jpeg format")

    payload = await request.body()
    folder = await FolderEntity.load(project_name, folder_id)
    # TODO: ACL here
    query = f"""
        INSERT INTO project_{project_name}.thumbnails (id, mime, data)
        VALUES ($1, $2, $3)
        ON CONFLICT (id)
        DO UPDATE SET data = EXCLUDED.data
    """
    await Postgres.execute(query, folder.id, content_type, payload)
    return Response(status_code=201)


@router.get(
    "/projects/{project_name}/folders/{folder_id}/thumbnail",
    response_class=Response,
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
        404: ResponseFactory.error(404),
    },
)
async def get_folder_thumbnail(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    folder = await FolderEntity.load(project_name, folder_id)
    # TODO: ACL
    query = f"SELECT mime, data FROM project_{project_name}.thumbnails WHERE id = $1"
    async for record in Postgres.iterate(query, folder.id):
        return Response(
            media_type=record["mime"], status_code=200, content=record["data"]
        )
    raise RecordNotFoundException(f"Thumbnail for folder {folder.id} does not exist")
