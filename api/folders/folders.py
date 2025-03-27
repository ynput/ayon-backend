from fastapi import BackgroundTasks, Query

from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import FolderEntity
from ayon_server.operations.project_level import ProjectLevelOperations

from .router import router

#
# [GET]
#


@router.get("/{folder_id}", response_model_exclude_none=True)
async def get_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
) -> FolderEntity.model.main_model:  # type: ignore
    """Retrieve a folder by its ID."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_read_access(user)
    return folder.as_user(user)


#
# [POST]
#


@router.post("", status_code=201)
async def create_folder(
    post_data: FolderEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new folder."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.create("folder", **post_data.dict(exclude_unset=True))
    res = await ops.process(can_fail=False, raise_on_error=True)
    folder_id = res.operations[0].entity_id
    assert folder_id is not None, "Folder ID is None. This should never happen."
    return EntityIdResponse(id=folder_id)


#
# [PATCH]
#


@router.patch("/{folder_id}", status_code=204)
async def update_folder(
    post_data: FolderEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a folder.

    Once there is a version published, the folder's name and hierarchy
    cannot be changed.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.update("folder", folder_id, **post_data.dict(exclude_unset=True))
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
    force: bool = Query(False, description="Allow recursive deletion"),
) -> EmptyResponse:
    """Delete a folder.

    Returns 409 error in there's a published product in the folder or any of
    its subfolders. Otherwise, deletes the folder and all its subfolders.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.delete("folder", folder_id, force=force)
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()
