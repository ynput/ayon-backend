from typing import Any

from fastapi import BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, ProjectName, RepresentationID
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import RepresentationEntity
from ayon_server.events import EventStream
from ayon_server.events.patch import build_pl_entity_change_events

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
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new representation."""

    representation = RepresentationEntity(
        project_name=project_name, payload=post_data.dict()
    )
    await representation.ensure_create_access(user)
    event = {
        "topic": "entity.representation.created",
        "description": f"Representation {representation.name} created",
        "summary": {
            "entityId": representation.id,
            "parentId": representation.parent_id,
        },
        "project": project_name,
    }
    await representation.save()
    background_tasks.add_task(
        EventStream.dispatch,
        sender=x_sender,
        user=user.name,
        **event,  # type: ignore
    )
    return EntityIdResponse(id=representation.id)


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
    x_sender: str | None = Header(default=None),
):
    """Patch (partially update) a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_update_access(user)
    events = build_pl_entity_change_events(representation, post_data)
    representation.patch(post_data)
    await representation.save()
    for event in events:
        background_tasks.add_task(
            EventStream.dispatch,
            sender=x_sender,
            user=user.name,
            **event,
        )
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
    x_sender: str | None = Header(default=None),
):
    """Delete a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_delete_access(user)
    event: dict[str, Any] = {
        "topic": "entity.representation.deleted",
        "description": f"Representation {representation.name} deleted",
        "summary": {
            "entityId": representation.id,
            "parentId": representation.parent_id,
        },
        "project": project_name,
    }
    await representation.delete()
    background_tasks.add_task(
        EventStream.dispatch,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
