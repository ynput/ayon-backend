from fastapi import BackgroundTasks, Depends, Header, Response

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_representation_id,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import RepresentationEntity, UserEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

from .router import router

#
# [GET]
#


@router.get(
    "/projects/{project_name}/representations/{representation_id}",
    response_model=RepresentationEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Representations not found")},
)
async def get_representation(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
):
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
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_representation(
    post_data: RepresentationEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    x_sender: str | None = Header(default=None),
):
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
    }
    await representation.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=representation.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/representations/{representation_id}",
    status_code=204,
    response_class=Response,
)
async def update_representation(
    post_data: RepresentationEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
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
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/representations/{representation_id}",
    response_class=Response,
    status_code=204,
)
async def delete_representation(
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
    x_sender: str | None = Header(default=None),
):
    """Delete a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_delete_access(user)
    event = {
        "topic": "entity.representation.deleted",
        "description": f"Representation {representation.name} deleted",
        "summary": {
            "entityId": representation.id,
            "parentId": representation.parent_id,
        },
    }
    await representation.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return Response(status_code=204)
