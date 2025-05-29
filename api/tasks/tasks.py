from typing import Any, Literal

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
from ayon_server.exceptions import ForbiddenException
from ayon_server.operations.project_level import ProjectLevelOperations
from ayon_server.types import Field, OPModel

from .router import router

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
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
) -> EntityIdResponse:
    """Create a new task.

    Use a POST request to create a new task (with a new id).
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.create("task", **post_data.dict(exclude_unset=True))
    res = await ops.process(can_fail=False, raise_on_error=True)
    entity_id = res.operations[0].entity_id
    return EntityIdResponse(id=entity_id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/tasks/{task_id}", status_code=204)
async def update_task(
    post_data: TaskEntity.model.patch_model,  # type: ignore
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Patch (partially update) a task."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.update("task", task_id, **post_data.dict(exclude_unset=True))
    await ops.process(can_fail=False, raise_on_error=True)
    return EmptyResponse()


#
# [DELETE]
#


@router.delete("/projects/{project_name}/tasks/{task_id}", status_code=204)
async def delete_task(
    user: CurrentUser,
    project_name: ProjectName,
    task_id: TaskID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete a task."""

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )
    ops.delete("task", task_id)
    await ops.process(can_fail=False, raise_on_error=True)
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
