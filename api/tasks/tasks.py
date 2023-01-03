from typing import Literal

from fastapi import APIRouter, Depends, Response

from ayon_server.api.dependencies import dep_current_user, dep_project_name, dep_task_id
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import TaskEntity, UserEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.types import Field, OPModel

router = APIRouter(
    tags=["Tasks"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/tasks/{task_id}",
    response_model=TaskEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Tasks not found")},
)
async def get_task(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    task_id: str = Depends(dep_task_id),
):
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
    responses={
        # TODO: check - will this happen only when the folderId is invalid?
        409: ResponseFactory.error(409, "Specified folder does not exist"),
    },
)
async def create_task(
    post_data: TaskEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new task.

    Use a POST request to create a new task (with a new id).
    """

    task = TaskEntity(project_name=project_name, payload=post_data.dict())
    # TODO: how to solve access control?
    await task.save()
    return EntityIdResponse(id=task.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/tasks/{task_id}",
    status_code=204,
    response_class=Response,
)
async def update_task(
    post_data: TaskEntity.model.patch_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    task_id: str = Depends(dep_task_id),
):
    """Patch (partially update) a task."""

    task = await TaskEntity.load(project_name, task_id)
    await task.ensure_update_access(user)
    task.patch(post_data)
    await task.save()
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/tasks/{task_id}",
    response_class=Response,
    status_code=204,
)
async def delete_task(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    task_id: str = Depends(dep_task_id),
):
    """Delete a task."""

    task = await TaskEntity.load(project_name, task_id)
    await task.delete()
    return Response(status_code=204)


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


@router.post(
    "/projects/{project_name}/tasks/{task_id}/assign",
    status_code=204,
    response_class=Response,
)
async def assign_users_to_task(
    post_data: AssignUsersRequestModel,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    task_id: str = Depends(dep_task_id),
):
    """Change the list of users assigned to a task."""

    if not user.is_manager and post_data.users != [user.name]:
        raise ForbiddenException("Normal users can only assign themselves")

    task = await TaskEntity.load(project_name, task_id)
    assignees = task.assignees

    if post_data.mode == "add":
        assignees.extend(post_data.users)
        # Remove duplicates
        assignees = list(dict.fromkeys(assignees))
    elif post_data.mode == "remove":
        assignees = [
            assignee for assignee in assignees if assignee not in post_data.users
        ]
    elif post_data.mode == "set":
        assignees = post_data.users
    else:
        raise ValueError(f"Unknown mode: {post_data.mode}")

    task.assignees = assignees
    await task.save()

    return Response(status_code=204)
