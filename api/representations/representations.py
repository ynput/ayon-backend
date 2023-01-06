from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response
from nxtools import logging

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_representation_id,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import RepresentationEntity, UserEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

router = APIRouter(
    tags=["Representations"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

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
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new representation."""

    representation = RepresentationEntity(
        project_name=project_name, payload=post_data.dict()
    )
    await representation.ensure_create_access(user)
    await representation.save()
    logging.info(f"[POST] Created representation {representation.name}", user=user.name)
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
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    representation_id: str = Depends(dep_representation_id),
):
    """Delete a representation."""

    representation = await RepresentationEntity.load(project_name, representation_id)
    await representation.ensure_delete_access(user)
    await representation.delete()
    logging.info(
        f"[DELETE] Deleted representation {representation.name}", user=user.name
    )
    return Response(status_code=204)
