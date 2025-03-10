from fastapi import BackgroundTasks

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    RepresentationID,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import RepresentationEntity
from ayon_server.operations.project_level import ProjectLevelOperations

from .router import router

#
# [GET]
#


@router.get(
    "/projects/{project_name}/representations/{representation_id}",
    response_model_exclude_none=True,
)
async def get_representation(
    user: CurrentUser,
    project_name: ProjectName,
    representation_id: RepresentationID,
) -> RepresentationEntity.model.main_model:  # type: ignore
    """Retrieve a representation by its ID."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_read_access(user)
    return representation.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/representations",
    status_code=201,
    response_model=EntityIdResponse,
)
async def create_representation(
    post_data: RepresentationEntity.model.post_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new representation."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.create("representation", **post_data.dict(exclude_unset=True))
    res = await ops.process(can_fail=False, raise_on_error=True)
    entity_id = res.operations[0].entity_id
    return EntityIdResponse(id=entity_id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/representations/{representation_id}", status_code=204
)
async def update_representation(
    post_data: RepresentationEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    representation_id: RepresentationID,
    sender: Sender,
    sender_type: SenderType,
):
    """Patch (partially update) a representation."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.update(
        "representation",
        representation_id,
        **post_data.dict(exclude_unset=True),
    )
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/representations/{representation_id}", status_code=204
)
async def delete_representation(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    representation_id: RepresentationID,
    sender: Sender,
    sender_type: SenderType,
):
    """Delete a representation."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.delete("representation", representation_id)
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()
