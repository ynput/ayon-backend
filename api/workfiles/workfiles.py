from fastapi import APIRouter, BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, ProjectName, WorkfileID
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import WorkfileEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

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
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new version.

    Use a POST request to create a new version (with a new id).
    """

    workfile = WorkfileEntity(project_name=project_name, payload=post_data.dict())
    await workfile.ensure_create_access(user)
    event = {
        "topic": "entity.workfile.created",
        "description": f"Workfile {workfile.name} created",
        "summary": {"entityId": workfile.id, "parentId": workfile.parent_id},
        "project": project_name,
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


@router.patch("/projects/{project_name}/workfiles/{workfile_id}", status_code=204)
async def update_workfile(
    post_data: WorkfileEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
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
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/workfiles/{workfile_id}", status_code=204)
async def delete_workfile(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    workfile_id: WorkfileID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Delete a workfile."""

    workfile = await WorkfileEntity.load(project_name, workfile_id)
    await workfile.ensure_delete_access(user)
    event = {
        "topic": "entity.workfile.deleted",
        "description": f"Workfile {workfile.name} deleted",
        "summary": {"entityId": workfile.id, "parentId": workfile.parent_id},
        "project": project_name,
    }
    await workfile.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
