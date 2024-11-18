from typing import Any

from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.entities import UserEntity
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

from .common import OperationType
from .router import router


class ActivityOperationModel(OPModel):
    id: str = Field(
        default_factory=create_uuid,
        title="Operation ID",
        description="identifier manually or automatically assigned to each operation",
    )
    type: OperationType = Field(
        ...,
        title="Operation type",
    )
    activity_id: str | None = Field(
        None,
        title="Activity ID",
        description="ID of the activity. None for create",
    )
    data: dict[str, Any] | None = Field(
        None,
        title="Data",
        description="Data to be used for create or update. Ignored for delete.",
    )


class ActivityOperationsRequestModel(OPModel):
    operations: list[ActivityOperationModel] = Field(default_factory=list)
    can_fail: bool = False


class ActivityOperationResponseModel(OPModel):
    id: str = Field(..., title="Operation ID")
    type: OperationType = Field(..., title="Operation type")
    success: bool = Field(..., title="Operation success")
    status: int | None = Field(None, title="HTTP-like status code")
    detail: str | None = Field(None, title="Error message")
    activity_id: str | None = Field(
        None,
        title="Entity ID",
        description="`None` if type is `create` and the operation fails.",
    )


class ActivityOperationsResponseModel(OPModel):
    operations: list[ActivityOperationResponseModel] = Field(default_factory=list)
    success: bool = Field(..., title="Overall success")


async def process_activity_operation(
    project_name: str,
    operation: ActivityOperationModel,
    user: UserEntity,
) -> ActivityOperationResponseModel:
    if operation.type == "create":
        entity_class = get_entity_class(operation.data["entity_type"])
        entity = await entity_class.load(project_name, operation.data["entity_id"])
        _ = entity
    elif operation.type == "update":
        pass
    elif operation.type == "delete":
        pass

    raise NotImplementedError("Operation type not implemented")


@router.post("/projects/{project_name}/operations/activities")
async def operations(
    user: CurrentUser,
    project_name: ProjectName,
    payload: ActivityOperationsRequestModel,
    sender: Sender,
    sender_type: SenderType,
) -> ActivityOperationsResponseModel:
    """
    Perform multiple operations on activities.

    - **operations**: List of operations to perform.
    - **can_fail**: If `True`, continue with other operations if one fails.
    """

    responses = []
    success = True
    for operation in payload.operations:
        response = await process_activity_operation(project_name, operation, user)
        responses.append(response)
        if not response.success:
            success = False
            if not payload.can_fail:
                break

    return ActivityOperationsResponseModel(
        operations=responses,
        success=success,
    )
