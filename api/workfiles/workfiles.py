from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response
from nxtools import logging

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_workfile_id,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import UserEntity, WorkfileEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

router = APIRouter(
    tags=["Workfiles"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/workfiles/{workfile_id}",
    response_model=WorkfileEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Versions not found")},
)
async def get_workfile(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    workfile_id: str = Depends(dep_workfile_id),
):
    """Retrieve a version by its ID."""

    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_read_access(user)
    return workfile.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/workfiles",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Conflict"),
    },
)
async def create_workfile(
    post_data: WorkfileEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    x_sender: str | None = Header(default=None),
):
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    workfile = WorkfileEntity(project_name=project_name, payload=post_data.dict())
    await workfile.ensure_create_access(user)
    event = {
        "topic": "entity.workfile.created",
        "description": f"Workfile {workfile.name} created",
        "summary": {"entityId": workfile.id, "parentId": workfile.parent_id},
    }
    await workfile.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=workfile.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/workfiles/{workfile_id}",
    status_code=204,
    response_class=Response,
)
async def update_workfile(
    post_data: WorkfileEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    workfile_id: str = Depends(dep_workfile_id),
    x_sender: str | None = Header(default=None),
):
    """Patch (partially update) a workfile."""

    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_update_access(user)
    events = build_pl_entity_change_events(workfile, post_data)
    workfile.patch(post_data)
    await workfile.save()
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
    "/projects/{project_name}/workfiles/{workfile_id}",
    response_class=Response,
    status_code=204,
)
async def delete_workfile(
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    workfile_id: str = Depends(dep_workfile_id),
    x_sender: str | None = Header(default=None),
):
    """Delete a workfile."""

    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_delete_access(user)
    event = {
        "topic": "entity.workfile.deleted",
        "description": f"Workfile {workfile.name} deleted",
        "summary": {"entityId": workfile.id, "parentId": workfile.parent_id},
    }
    await workfile.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return Response(status_code=204)
