from typing import Literal

from fastapi import BackgroundTasks

from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.lib.redis import Redis
from ayon_server.operations.project_level import (
    OperationModel,
    OperationsResponseModel,
    ProjectLevelOperations,
)
from ayon_server.types import Field, OPModel
from ayon_server.utils.hashing import create_uuid

from .router import router

BACKGROUND_OPS_TTL = 600  # 10 minutes


class OperationsRequestModel(OPModel):
    operations: list[OperationModel] = Field(default_factory=list)
    can_fail: bool = False
    wait_for_events: bool = False
    raise_on_error: bool = False


@router.post(
    "/projects/{project_name}/operations",
    response_model=OperationsResponseModel,
)
async def operations(
    payload: OperationsRequestModel,
    project_name: ProjectName,
    user: CurrentUser,
    sender: Sender,
    sender_type: SenderType,
):
    """
    Process multiple operations (create / update / delete) in a single request.

    All operations are processed in the order they are provided in the request.
    If can_fail is set to False, the processing stops on the first error and
    all previous operations are rolled back. If can_fail is set to True, the
    processing continues and all operations are committed.

    The response contains the list of operations with their success status.
    In case of failure, the error message is provided for each operation.

    This endpoint normally does not return error response, unless there is
    a problem with the request itself or an unhandled exception.
    Do not rely on a status code to determine if the operation was successful.

    Always check the `success` field of the response.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    for operation in payload.operations:
        if operation.as_user:
            is_different_user = operation.as_user != user.name
            if is_different_user and not user.is_service:
                msg = "You are not allowed to perform operations as another user"
                raise ForbiddenException(msg)
        ops.append(operation)

    # Return an error response ONLY if:
    #  - can_fail is set to False
    #  - raise_on_error is set to True
    #
    #  Otherwise, the endpoint will return a success response
    #  regardless of the operations' success and the errors
    #  are included in the response (default behavior).

    raise_on_error = False
    if not payload.can_fail:
        raise_on_error = payload.raise_on_error

    return await ops.process(
        can_fail=payload.can_fail,
        raise_on_error=raise_on_error,
        wait_for_events=payload.wait_for_events,
    )


#
# Background tasks variant
#


class BackgroundOperationsResponseModel(OPModel):
    id: str
    status: Literal["pending", "in_progress", "completed"] = "pending"
    result: OperationsResponseModel | None = None


async def _execute_background_operations(
    task_id: str,
    ops: ProjectLevelOperations,
    *,
    can_fail: bool,
) -> None:
    await Redis.set_json(
        "background-operations",
        task_id,
        {"status": "in_progress"},
        ttl=BACKGROUND_OPS_TTL,
    )
    response = await ops.process(
        can_fail=can_fail,
        raise_on_error=False,
        wait_for_events=True,
    )
    await Redis.set_json(
        "background-operations",
        task_id,
        {"status": "completed", "result": response.dict()},
        ttl=BACKGROUND_OPS_TTL,
    )


@router.post("/projects/{project_name}/operations/background")
async def background_operations(
    payload: OperationsRequestModel,
    project_name: ProjectName,
    user: CurrentUser,
    sender: Sender,
    sender_type: SenderType,
    background_tasks: BackgroundTasks,
) -> BackgroundOperationsResponseModel:
    """
    The same as `POST /projects/{project_name}/operations` but runs in the background.
    The response is returned immediately and contains a task ID that can be used to
    query the status of the task.
    """

    ops = ProjectLevelOperations(
        project_name,
        user=user,
        sender=sender,
        sender_type=sender_type,
    )

    for operation in payload.operations:
        if operation.as_user:
            is_different_user = operation.as_user != user.name
            if is_different_user and not user.is_service:
                msg = "You are not allowed to perform operations as another user"
                raise ForbiddenException(msg)
        ops.append(operation)

    task_id = create_uuid()

    background_tasks.add_task(
        _execute_background_operations,
        task_id,
        ops,
        can_fail=payload.can_fail,
    )

    await Redis.set_json(
        "background-operations",
        task_id,
        {"status": "pending"},
        ttl=BACKGROUND_OPS_TTL,
    )
    return BackgroundOperationsResponseModel(id=task_id)


@router.get("/projects/{project_name}/operations/background/{task_id}")
async def get_background_operations_status(
    project_name: ProjectName,
    task_id: str,
    user: CurrentUser,
) -> BackgroundOperationsResponseModel:
    """Get the status of a background operations task."""

    # Note: project_name is not used here but kept for consistency
    # and future use (if needed).
    _ = project_name, user

    data = await Redis.get_json("background-operations", task_id)
    if not data:
        msg = f"Background operations task '{task_id}' not found"
        raise NotFoundException(msg)

    return BackgroundOperationsResponseModel(id=task_id, **data)
