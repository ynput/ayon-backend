from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks

from ayon_server.api.dependencies import (
    CurrentUser,
    ProjectName,
    Sender,
    SenderType,
    TaskID,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.config import ayonconfig
from ayon_server.entities import TaskEntity
from ayon_server.events import EventStream
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import Field, OPModel

router = APIRouter(tags=["Tasks"])

#
# [GET]
#


@router.get(
    "/projects/{project_name}/tasks/{task_id}",
    response_model_exclude_none=True,
)
async def get_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
) -> TaskEntity.model.main_model:  # type: ignore
    """Retrieve a task by its ID."""

    task = await TaskEntity.load(project_name, task_id)
    await task.ensure_read_access(user)
    return task.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/tasks",
    status_code=201,
    response_model=EntityIdResponse,
)
async def create_task(
    post_data: TaskEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new task.

    Use a POST request to create a new task (with a new id).
    """

    task = TaskEntity(project_name=project_name, payload=post_data.dict())
    await task.ensure_create_access(user)
    event: dict[str, Any] = {
        "topic": "entity.task.created",
        "description": f"Task {task.name} created",
        "summary": {"entityId": task.id, "parentId": task.parent_id},
        "project": project_name,
    }
    await task.save()
    background_tasks.add_task(
        EventStream.dispatch,
        sender=sender,
        sender_type=sender_type,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=task.id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/tasks/{task_id}", status_code=204)
async def update_task(
    post_data: TaskEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a task."""

    task = await TaskEntity.load(project_name, task_id)
    await task.ensure_update_access(user)
    events = build_pl_entity_change_events(task, post_data)
    task.patch(post_data)
    await task.save()
    for event in events:
        background_tasks.add_task(
            EventStream.dispatch,
            sender=sender,
            sender_type=sender_type,
            user=user.name,
            **event,
        )
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/tasks/{task_id}", status_code=204)
async def delete_task(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a task."""

    task = await TaskEntity.load(project_name, task_id)
    event: dict[str, Any] = {
        "topic": "entity.task.deleted",
        "description": f"Task {task.name} deleted",
        "summary": {"entityId": task.id, "parentId": task.parent_id},
        "project": project_name,
    }
    if ayonconfig.audit_trail:
        event["payload"] = {"entityData": task.dict_simple()}
    await task.delete()
    background_tasks.add_task(
        EventStream.dispatch,
        sender=sender,
        sender_type=sender_type,
        user=user.name,
        **event,
    )
    return EmptyResponse()


#
# Assign
#


class AssignUsersRequestModel(OPModel):
    """Assign users to a task."""

    mode: Literal["add", "remove", "set"] = Field(
        ...,
        description="What to do with the list of users",
        example="add",
    )
    users: list[str] = Field(
        ...,
        description="List of user names",
        example=["Eeny", "Meeny", "Miny", "Moe"],
    )


@router.post("/projects/{project_name}/tasks/{task_id}/assign", status_code=204)
async def assign_users_to_task(
    post_data: AssignUsersRequestModel,
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
) -> EmptyResponse:
    """Change the list of users assigned to a task."""

    if not user.is_manager and post_data.users != [user.name]:  # TBD
        raise ForbiddenException("Normal users can only assign themselves")

    task = await TaskEntity.load(project_name, task_id)
    assignees = set(task.assignees)
    original_assignees = set(task.assignees)

    if post_data.mode == "add":
        assignees.update(post_data.users)
    elif post_data.mode == "remove":
        for uname in post_data.users:
            assignees.discard(uname)
    elif post_data.mode == "set":
        assignees = set(post_data.users)
    else:
        raise ValueError(f"Unknown mode: {post_data.mode}")

    if assignees == original_assignees:
        # nothing changed
        return EmptyResponse()

    task.assignees = list(assignees)
    await task.save()

    event_payload: dict[str, Any] = {
        "description": f"Changed task {task.name} assignees",
        "project": project_name,
        "summary": {"entityId": task.id, "parentId": task.folder_id},
        "user": user.name,
    }
    if ayonconfig.audit_trail:
        event_payload["payload"] = {
            "oldValue": list(original_assignees),
            "newValue": list(assignees),
        }

    await EventStream.dispatch("entity.task.assignees_changed", **event_payload)

    return EmptyResponse()
