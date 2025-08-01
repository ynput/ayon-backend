from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.exceptions import ForbiddenException
from ayon_server.operations.project_level import (
    OperationModel,
    OperationsResponseModel,
    ProjectLevelOperations,
)
from ayon_server.types import Field, OPModel

from .router import router


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
