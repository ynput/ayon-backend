from fastapi import APIRouter, Depends, Response

from openpype.access.utils import folder_access_list

from openpype.api.dependencies import dep_current_user, dep_folder_id, dep_project_name
from openpype.api.responses import ResponseFactory, EntityIdResponse

from openpype.entities import FolderEntity, UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres

router = APIRouter(
    tags=["Folders"],
    responses={401: ResponseFactory.error(401), 403: ResponseFactory.error(403)},
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/folders/{folder_id}",
    response_model=FolderEntity.model.main_model,
    responses={404: ResponseFactory.error(404, "Project not found")},
)
async def get_folder(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Retrieve a folder by its ID."""

    folder = await FolderEntity.load(project_name, folder_id)
    access_list = await folder_access_list(user, project_name, "read")

    if access_list is not None:
        if folder.path not in access_list:
            raise ForbiddenException("You don't have access to this folder")

    return folder.payload


#
# [POST]
#


@router.post(
    "/projects/{project_name}/folders",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_folder(
    post_data: FolderEntity.model.post_model,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new folder.

    Use a POST request to create a new folder (with a new id).
    """

    # TODO: Access control

    folder = FolderEntity(project_name=project_name, **post_data.dict())
    await folder.save()
    return EntityIdResponse(id=folder.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/folders/{folder_id}",
    status_code=204,
    response_class=Response,
)
async def update_folder(
    post_data: FolderEntity.model.patch_model,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Patch (partially update) a folder."""

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            folder = await FolderEntity.load(
                project_name, folder_id, transaction=conn, for_update=True
            )

            access_list = await folder_access_list(user, project_name, "write")

            if access_list is not None:
                if folder.path not in access_list:
                    raise ForbiddenException(403)

            folder.patch(post_data)
            await folder.save(transaction=conn)

    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/folders/{folder_id}",
    response_class=Response,
    status_code=204,
)
async def delete_folder(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Delete a folder."""

    folder = await FolderEntity.load(project_name, folder_id)
    access_list = await folder_access_list(user, project_name, "write")

    if access_list is not None:
        if folder.path not in access_list:
            raise ForbiddenException("You are not allowed to delete this folder")

    await folder.delete()
    return Response(status_code=204)
