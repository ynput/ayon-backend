from fastapi import APIRouter

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
    WorkfileID,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import WorkfileEntity
from ayon_server.operations.project_level import ProjectLevelOperations

router = APIRouter(tags=["Workfiles"])

#
# [GET]
#


@router.get(
    "/projects/{project_name}/workfiles/{workfile_id}",
    response_model_exclude_none=True,
)
async def get_workfile(
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
) -> WorkfileEntity.model.main_model:  # type: ignore
    """Retrieve a version by its ID."""

    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_read_access(user)
    return workfile.as_user(user)


#
# [POST]
#


@router.post("/projects/{project_name}/workfiles", status_code=201)
async def create_workfile(
    post_data: WorkfileEntity.model.post_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new workfile.

    Use a POST request to create a new workfile
    """

    if not post_data.created_by:
        post_data.created_by = user.name
    if not post_data.updated_by:
        post_data.updated_by = post_data.created_by

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.create("workfile", **post_data.dict(exclude_unset=True))
    res = await ops.process(can_fail=False, raise_on_error=True)
    entity_id = res.operations[0].entity_id
    return EntityIdResponse(id=entity_id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/workfiles/{workfile_id}", status_code=204)
async def update_workfile(
    post_data: WorkfileEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a workfile."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.update("workfile", workfile_id, **post_data.dict(exclude_unset=True))
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/workfiles/{workfile_id}", status_code=204)
async def delete_workfile(
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a workfile."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.delete("workfile", workfile_id)
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()
