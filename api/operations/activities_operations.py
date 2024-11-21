from datetime import datetime
from typing import Any

from ayon_server.activities import (
    ActivityType,
    create_activity,
    delete_activity,
    update_activity,
)
from ayon_server.api.dependencies import CurrentUser, ProjectName, Sender, SenderType
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

from .common import OperationType
from .router import router

# Payload models: this is just a copy of the models from api/activities/activity.py
# TODO: refactor - move these models to a shared location


class ProjectActivityPostModel(OPModel):
    id: str | None = Field(None, description="Explicitly set the ID of the activity")
    activity_type: ActivityType = Field(..., example="comment")
    body: str = Field("", example="This is a comment")
    files: list[str] | None = Field(None, example=["file1", "file2"])
    timestamp: datetime | None = Field(None, example="2021-01-01T00:00:00Z")
    data: dict[str, Any] | None = Field(
        None,
        example={"key": "value"},
        description="Additional data",
    )


class ActivityPatchModel(OPModel):
    body: str | None = Field(
        None,
        example="This is a comment",
        description="When set, update the activity body",
    )
    files: list[str] | None = Field(
        None,
        example=["file1", "file2"],
        description="When set, update the activity files",
    )
    append_files: bool = Field(
        False,
        example=False,
        description="When true, append files to the existing ones. replace them otherwise",  # noqa: E501
    )
    data: dict[str, Any] | None = Field(None, example={"key": "value"})


# Request/response models


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
        description="Data to be used for create or update. Ignored for delete."
        "See create/patch activity endpoint for details",
    )


class ActivityOperationsRequestModel(OPModel):
    operations: list[ActivityOperationModel] = Field(
        default_factory=list,
        example=[
            {
                "id": "1",
                "type": "create",
                "data": {
                    "entityType": "folder",
                    "entityId": "12345678901234567890123456789012",
                    "activity_type": "comment",
                    "body": "This is a comment",
                    "timestamp": "2021-01-01T00:00:00Z",
                    "files": ["12345678901234567890123456789012"],
                    "data": {"key": "value"},
                },
            },
            {
                "id": "2",
                "type": "update",
                "activityId": "12345678901234567890123456789012",
                "data": {
                    "body": "This is an updated comment",
                    "files": ["12345678901234567890123456789012"],
                    "append_files": True,
                    "data": {"key": "newvalue"},
                },
            },
            {
                "id": "3",
                "type": "delete",
                "activityId": "12345678901234567890123456789012",
            },
        ],
    )
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


# Process a single operation


async def process_activity_operation(
    project_name: str,
    operation: ActivityOperationModel,
    user: UserEntity,
    sender: str | None = None,
    sender_type: str | None = None,
) -> ActivityOperationResponseModel:
    if operation.type == "create":
        if not operation.data:
            raise BadRequestException("Data is required for create operation")

        try:
            activity = ProjectActivityPostModel(**operation.data)
        except Exception as e:
            raise BadRequestException(str(e))

        if not user.is_service:
            if activity.activity_type != "comment":
                raise ForbiddenException(
                    "Only service users can create activities of this type"
                )

        entity_class = get_entity_class(operation.data["entityType"])
        entity_id = operation.data.get("entityId", "").replace("-", "")
        if not len(entity_id) == 32:
            raise BadRequestException("Invalid entity ID")
        entity = await entity_class.load(project_name, operation.data["entityId"])

        try:
            id = await create_activity(
                entity=entity,
                activity_id=activity.id,
                activity_type=activity.activity_type,
                body=activity.body,
                files=activity.files,
                user_name=user.name,
                timestamp=activity.timestamp,
                sender=sender,
                sender_type=sender_type,
                data=activity.data,
            )
        except Exception as e:
            raise AyonException(str(e))

        return ActivityOperationResponseModel(
            id=operation.id,
            type=operation.type,
            success=True,
            activity_id=id,
        )

    elif operation.type == "update":
        if not operation.data:
            raise BadRequestException("Data is required for update operation")
        if not operation.activity_id:
            raise BadRequestException("Activity ID is required for update operation")

        try:
            patch = ActivityPatchModel(**operation.data)
        except Exception as e:
            raise BadRequestException(str(e))

        try:
            await update_activity(
                project_name,
                operation.activity_id,
                body=patch.body,
                files=patch.files,
                append_files=patch.append_files,
                user_name=user.name,
                is_admin=user.is_admin,
                sender=sender,
                sender_type=sender_type,
                data=patch.data,
            )
        except Exception as e:
            raise AyonException(str(e))

        return ActivityOperationResponseModel(
            id=operation.id,
            type=operation.type,
            success=True,
            activity_id=operation.activity_id,
        )

    elif operation.type == "delete":
        if not operation.activity_id:
            raise BadRequestException("Activity ID is required for delete operation")
        try:
            await delete_activity(
                project_name,
                operation.activity_id,
                user_name=user.name,
                is_admin=user.is_admin,
                sender=sender,
                sender_type=sender_type,
            )
        except Exception as e:
            raise AyonException(str(e))

        return ActivityOperationResponseModel(
            id=operation.id,
            type=operation.type,
            success=True,
            activity_id=operation.activity_id,
        )

    raise NotImplementedError("Operation type not implemented")


@router.post("/projects/{project_name}/operations/activities")
async def activities_operations(
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

    # TODO: run in transaction if can_fail is False and rollback on failure
    # This is currently not possible because activity funftions don't accept
    # a transaction argument

    responses = []
    success = True
    for operation in payload.operations:
        try:
            response = await process_activity_operation(
                project_name,
                operation,
                user,
                sender,
                sender_type,
            )
        except AyonException as e:
            response = ActivityOperationResponseModel(
                id=operation.id,
                type=operation.type,
                success=False,
                status=e.status,
                detail=e.detail,
                activity_id=None,
            )
        except Exception as e:
            response = ActivityOperationResponseModel(
                id=operation.id,
                type=operation.type,
                success=False,
                status=500,
                detail=str(e),
                activity_id=None,
            )

        responses.append(response)
        if not response.success:
            success = False
            if not payload.can_fail:
                break

    return ActivityOperationsResponseModel(
        operations=responses,
        success=success,
    )
