from fastapi import Depends, Response
from pydantic import BaseModel
from nxtools import log_traceback

from openpype.utils import EntityID
from openpype.entities import UserEntity, FolderEntity, ProjectEntity
from openpype.lib.postgres import Postgres
from openpype.exceptions import ConstraintViolationException, RecordNotFoundException
from openpype.api import (
    ResponseFactory,
    APIException,
    dep_project_name,
    dep_folder_id,
    dep_current_user,
)

from .router import router


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

    try:
        folder = await FolderEntity.load(project_name, folder_id)
    except RecordNotFoundException:
        raise APIException(404, "Folder not found")
    except Exception:
        log_traceback("Unable to load folder")
        raise APIException(500, "Unable to load folder")

    return folder.payload


#
# [POST]
#


class PostFolderResponseModel(BaseModel):
    id: str = EntityID.field("folder")


@router.post(
    "/projects/{project_name}/folders",
    status_code=201,
    response_model=PostFolderResponseModel,
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

    project = await ProjectEntity.load(project_name)
    if not user.can("modify", project):
        raise APIException(403, "You are not allowed to modify this project")

    folder = FolderEntity(project_name=project_name, **post_data.dict())
    try:
        await folder.save()
    except ConstraintViolationException as e:
        raise APIException(409, f"Unable to create folder. {e.detail}")
    return PostFolderResponseModel(id=folder.id)


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
            try:
                folder = await FolderEntity.load(
                    project_name, folder_id, transaction=conn, for_update=True
                )
            except RecordNotFoundException:
                raise APIException(404, "Folder not found")

            if not user.can("modify", folder):
                raise APIException(
                    403, f"You don't have permission to modify folder {folder.name}"
                )

            folder.patch(post_data)

            try:
                await folder.save(transaction=conn)
            except ConstraintViolationException as e:
                raise APIException(409, f"Unable to update folder. {e.detail}")

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

    try:
        folder = await FolderEntity.load(project_name, folder_id)
    except RecordNotFoundException:
        raise APIException(404, "Folder not found")

    if not user.can("delete", folder):
        raise APIException(403, "You are not allowed to delete this folder")

    await folder.delete()
    return Response(status_code=204)
