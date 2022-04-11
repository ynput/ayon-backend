from fastapi import APIRouter, Depends, Response

from openpype.api.dependencies import dep_current_user, dep_folder_id, dep_project_name
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import FolderEntity, UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres

router = APIRouter(
    tags=["Folders"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/folders/{folder_id}",
    operation_id="get_folder",
    response_model=FolderEntity.model.main_model,
    response_model_exclude_none=True,
    responses={
        404: ResponseFactory.error(404, "Project not found"),
    },
)
async def get_folder(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Retrieve a folder by its ID."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_read_access(user)
    return folder.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/folders",
    operation_id="create_folder",
    status_code=201,
    response_model=EntityIdResponse,
)
async def create_folder(
    post_data: FolderEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new folder.

    Use a POST request to create a new folder (with a new id).
    """

    folder = FolderEntity(project_name=project_name, payload=post_data.dict())

    if folder.parent_id is None:
        if not user.is_manager:
            raise ForbiddenException("Only managers can create root folders")
    else:
        parent_folder = await FolderEntity.load(project_name, folder.parent_id)
        await parent_folder.ensure_create_access(user)

    await folder.save()
    return EntityIdResponse(id=folder.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/folders/{folder_id}",
    operation_id="update_folder",
    status_code=204,
    response_class=Response,
)
async def update_folder(
    post_data: FolderEntity.model.patch_model,  # type: ignore
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

            await folder.ensure_update_access(user)
            folder.patch(post_data)
            await folder.save(transaction=conn)

    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/folders/{folder_id}",
    operation_id="delete_folder",
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
    folder.ensure_delete_access(user)

    await folder.delete()
    return Response(status_code=204)
