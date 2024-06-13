from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, ProjectName, VersionID
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import VersionEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException

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
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    payload = post_data.dict(exclude_unset=True)
    if "author" not in payload:
        payload["author"] = user.name

    if not user.is_admin:
        if payload["author"] != user.name:
            raise ForbiddenException(
                "You can only create versions for yourself, unless you are an admin."
            )

    version = VersionEntity(project_name=project_name, payload=payload)
    await version.ensure_create_access(user)
    event = {
        "topic": "entity.version.created",
        "description": f"Version {version.name} created",
        "summary": {"entityId": version.id, "parentId": version.parent_id},
        "project": project_name,
    }
    await version.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,  # type: ignore
    )
    return EntityIdResponse(id=version.id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/versions/{version_id}", status_code=204)
async def update_version(
    post_data: VersionEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Patch (partially update) a version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_update_access(user)
    events = build_pl_entity_change_events(version, post_data)
    version.patch(post_data)
    await version.save()
    for event in events:
        background_tasks.add_task(
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/versions/{version_id}", status_code=204)
async def delete_version(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    version_id: VersionID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Delete a version.

    This will also delete all representations of the version.
    """

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_delete_access(user)
    event: dict[str, Any] = {
        "topic": "entity.version.deleted",
        "description": f"Version {version.name} deleted",
        "summary": {"entityId": version.id, "parentId": version.parent_id},
        "project": project_name,
    }
    await version.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
