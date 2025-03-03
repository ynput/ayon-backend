from fastapi import APIRouter

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
    VersionID,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import VersionEntity
from ayon_server.operations.project_level import ProjectLevelOperations

router = APIRouter(tags=["Versions"])

#
# [GET]
#


@router.get(
    "/projects/{project_name}/versions/{version_id}", response_model_exclude_none=True
)
async def get_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
) -> VersionEntity.model.main_model:  # type: ignore
    """Retrieve a version by its ID."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_read_access(user)
    return version.as_user(user)


#
# [POST]
#


@router.post("/projects/{project_name}/versions", status_code=201)
async def create_version(
    post_data: VersionEntity.model.post_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    payload = post_data.dict(exclude_unset=True)
    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.create("version", **payload)
    res = await ops.process(can_fail=False, raise_on_error=True)
    version_id = res.operations[0].entity_id
    return EntityIdResponse(id=version_id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/versions/{version_id}", status_code=204)
async def update_version(
    post_data: VersionEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a version."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    ops.update("version", version_id, **post_data.dict(exclude_unset=True))
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/versions/{version_id}", status_code=204)
async def delete_version(
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a version.

    This will also delete all representations of the version.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.delete("version", version_id)
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()
