from typing import Any

from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

from .common import OperationType


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
