from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_version_id,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import UserEntity, VersionEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

router = APIRouter(
    tags=["Versions"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/versions/{version_id}",
    response_model=VersionEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Versions not found")},
)
async def get_version(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
):
    """Retrieve a version by its ID."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_read_access(user)
    return version.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/versions",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_version(
    post_data: VersionEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    x_sender: str | None = Header(default=None),
):
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    version = VersionEntity(project_name=project_name, payload=post_data.dict())
    await version.ensure_create_access(user)
    event = {
        "topic": "entity.version.created",
        "description": f"Version {version.name} created",
        "summary": {"entityId": version.id, "parentId": version.parent_id},
    }
    await version.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=version.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/versions/{version_id}",
    status_code=204,
    response_class=Response,
)
async def update_version(
    post_data: VersionEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
    x_sender: str | None = Header(default=None),
):
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
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/versions/{version_id}",
    response_class=Response,
    status_code=204,
)
async def delete_version(
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    version_id: str = Depends(dep_version_id),
    x_sender: str | None = Header(default=None),
):
    """Delete a version."""

    version = await VersionEntity.load(project_name, version_id)
    await version.ensure_delete_access(user)
    event = {
        "topic": "entity.version.deleted",
        "description": f"Version {version.name} deleted",
        "summary": {"entityId": version.id, "parentId": version.parent_id},
    }
    await version.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return Response(status_code=204)
