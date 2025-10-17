from typing import Annotated, Any, Literal

from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid

from ..common import OperationType


class OperationModel(OPModel):
    """Model for a single project-level operation.

    Operation type is one of create, update, delete.

    Each operation has a unique ID, that may be used to match the result
    in the response. The ID is automatically generated if not provided.

    The entity ID is required for update and delete operations, optional for create.
    The data field is required for create and update operations, ignored for delete.

    Force flag may be used for delete operations to force
    recursive deletion of the children entities (if applicable).
    """

    id: Annotated[str, Field(default_factory=create_uuid, title="Operation ID")]
    type: Annotated[OperationType, Field(title="Operation type")]
    entity_type: Annotated[ProjectLevelEntityType, Field(title="Entity type")]
    entity_id: Annotated[str | None, Field(title="Entity ID")] = None
    data: Annotated[dict[str, Any] | None, Field(title="Data")] = None
    force: Annotated[bool, Field(title="Force recursive deletion")] = False
    as_user: str | None = None


class OperationResponseModel(OPModel):
    """Response model for a single operation.

    Entity ID is `None` if the operation is a create and the operation fails.
    Status returns HTTP-like status code (201, 204, 404, etc.)
    """

    id: Annotated[str, Field(title="Operation ID")]
    type: Annotated[OperationType, Field(title="Operation type")]
    entity_type: Annotated[ProjectLevelEntityType, Field(title="Entity type")]
    entity_id: Annotated[str | None, Field(title="Entity ID")] = None
    success: Annotated[bool, Field(title="Operation success")]
    status: Annotated[int, Field(title="HTTP-like status code")]
    error_code: Annotated[str | None, Field(title="Error code")] = None
    detail: Annotated[str | None, Field(title="Error message")] = None


class OperationsResponseModel(OPModel):
    operations: Annotated[list[OperationResponseModel], Field(default_factory=list)]
    success: Annotated[bool, Field(title="Overall success")] = False


FieldType = Literal["field", "attribute"]


class FieldChangeModel(OPModel):
    type: Annotated[FieldType, Field(title="Type of the field")]
    name: Annotated[str, Field(title="Name of the field")]
