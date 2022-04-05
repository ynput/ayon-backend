from fastapi import APIRouter, Depends, Response

from openpype.api.dependencies import dep_current_user, dep_project_name, dep_task_id
from openpype.api.responses import EntityIdResponse, ResponseFactory
from openpype.entities import TaskEntity, UserEntity

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
    operation_id="get_task",
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
    operation_id="create_task",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
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
    await task.save()
    return EntityIdResponse(id=task.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/tasks/{task_id}",
    operation_id="update_task",
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
    task.patch(post_data)
    await task.save()
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/tasks/{task_id}",
    operation_id="delete_task",
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
