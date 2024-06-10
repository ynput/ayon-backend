from contextlib import suppress
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Header
from nxtools import log_traceback

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel, ProjectLevelEntityType
from ayon_server.utils import create_uuid

router = APIRouter(tags=["Projects"])


class RollbackException(Exception):
    pass


#
# Models
#

OperationType = Literal["create", "update", "delete"]


class OperationModel(OPModel):
    id: str = Field(
        default_factory=create_uuid,
        title="Operation ID",
        description="identifier manually or automatically assigned to each operation",
    )
    type: OperationType = Field(
        ...,
        title="Operation type",
    )
    entity_type: ProjectLevelEntityType = Field(
        ...,
        title="Entity type",
    )
    entity_id: str | None = Field(
        None,
        title="Entity ID",
        description="ID of the entity. None for create",
    )
    data: dict[str, Any] | None = Field(
        None,
        title="Data",
        description="Data to be used for create or update. Ignored for delete.",
    )
    force: bool = Field(False, title="Force recursive deletion")


class OperationsRequestModel(OPModel):
    operations: list[OperationModel] = Field(default_factory=list)
    can_fail: bool = False


class OperationResponseModel(OPModel):
    id: str = Field(..., title="Operation ID")
    type: OperationType = Field(..., title="Operation type")
    success: bool = Field(..., title="Operation success")
    status: int | None = Field(None, title="HTTP-like status code")
    detail: str | None = Field(None, title="Error message")
    entity_type: ProjectLevelEntityType = Field(..., title="Entity type")
    entity_id: str | None = Field(
        None,
        title="Entity ID",
        description="`None` if type is `create` and the operation fails.",
    )


class OperationsResponseModel(OPModel):
    operations: list[OperationResponseModel] = Field(default_factory=list)
    success: bool = Field(..., title="Overall success")


#
# Processing
#


async def process_operation(
    project_name: str,
    user: UserEntity,
    operation: OperationModel,
    transaction=None,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]] | None, OperationResponseModel]:
    """Process a single operation. Raise an exception on error."""

    entity_class = get_entity_class(operation.entity_type)

    # Data for the event triggered after successful operation
    events: list[dict[str, Any]] | None = None

    if operation.type == "create":
        assert operation.data is not None, "data is required for create"
        payload = entity_class.model.post_model(**operation.data)
        payload_dict = payload.dict()
        if operation.entity_id is not None:
            payload_dict["id"] = operation.entity_id
        if operation.entity_type == "version":
            if not payload_dict.get("author"):
                payload_dict["author"] = user.name
        elif operation.entity_type == "workfile":
            if not payload_dict.get("created_by"):
                payload_dict["created_by"] = user.name
            if not payload_dict.get("updated_by"):
                payload_dict["updated_by"] = payload_dict["created_by"]
        entity = entity_class(project_name, payload_dict)
        await entity.ensure_create_access(user)
        description = f"{operation.entity_type.capitalize()} {entity.name} created"
        events = [
            {
                "topic": f"entity.{operation.entity_type}.created",
                "summary": {"entityId": entity.id, "parentId": entity.parent_id},
                "description": description,
                "project": project_name,
            }
        ]
        await entity.save(transaction=transaction)

    elif operation.type == "update":
        # in this case, thumbnailId is camelCase, since we pass a dict
        assert operation.data is not None, "data is required for update"
        thumbnail_only = len(operation.data) == 1 and "thumbnailId" in operation.data

        payload = entity_class.model.patch_model(**operation.data)
        assert operation.entity_id is not None, "entity_id is required for update"

        if operation.entity_type == "workfile":
            if not payload.updated_by:  # type: ignore
                payload.updated_by = user.name

        entity = await entity_class.load(
            project_name,
            operation.entity_id,
            for_update=True,
            transaction=transaction,
        )
        await entity.ensure_update_access(user, thumbnail_only=thumbnail_only)
        events = build_pl_entity_change_events(entity, payload)
        entity.patch(payload)
        await entity.save(transaction=transaction)

    elif operation.type == "delete":
        assert operation.entity_id is not None, "entity_id is required for delete"
        entity = await entity_class.load(project_name, operation.entity_id)
        await entity.ensure_delete_access(user)
        description = f"{operation.entity_type.capitalize()} {entity.name} deleted"

        if operation.force and not user.is_manager:
            raise ForbiddenException("Only managers can force delete")

        events = [
            {
                "topic": f"entity.{operation.entity_type}.deleted",
                "summary": {"entityId": entity.id, "parentId": entity.parent_id},
                "description": description,
                "project": project_name,
            }
        ]
        if ayonconfig.audit_trail:
            events[0]["payload"] = {"entityData": entity.dict_simple()}
        await entity.delete(transaction=transaction, force=operation.force)
    else:
        raise BadRequestException(f"Unknown operation type {operation.type}")

    return (
        entity,
        events,
        OperationResponseModel(
            success=True,
            id=operation.id,
            type=operation.type,
            entity_id=entity.id,
            entity_type=operation.entity_type,
        ),
    )


async def process_operations(
    project_name: str,
    user: UserEntity,
    operations: list[OperationModel],
    can_fail: bool = False,
    transaction=None,
) -> tuple[list[dict[str, Any]], OperationsResponseModel]:
    """Process a list of operations.

    This is separated from the endpoint so the endpoint can
    run this operation within or without a transaction context.

    This function should not raise an exception. If an operation
    fails, success=False is returned.
    """

    result: list[OperationResponseModel] = []
    to_commit: list[ProjectLevelEntity] = []

    events: list[dict[str, Any]] = []

    for _i, operation in enumerate(operations):
        try:
            entity, evt, response = await process_operation(
                project_name,
                user,
                operation,
                transaction=transaction,
            )
            if evt is not None:
                events.extend(evt)
            result.append(response)
            if entity.entity_type not in [e.entity_type for e in to_commit]:
                to_commit.append(entity)
        except AyonException as e:
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=e.status,
                    detail=e.detail,
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )
            if not can_fail:
                break
        except Exception as exc:
            log_traceback()
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=500,
                    detail=str(exc),
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )

            if not can_fail:
                # No need to continue
                break

    for op in result:
        if op.status:
            continue
        elif op.type == "create":
            op.status = 201
        elif op.type == "update":
            op.status = 200
        elif op.type == "delete":
            op.status = 204

    # Create overall success value
    success = all(op.success for op in result)
    if success or can_fail:
        for entity in to_commit:
            await entity.commit(transaction=transaction)

    return events, OperationsResponseModel(operations=result, success=success)


#
# Operations request
#


@router.post(
    "/projects/{project_name}/operations",
    response_model=OperationsResponseModel,
)
async def operations(
    payload: OperationsRequestModel,
    background_tasks: BackgroundTasks,
    project_name: ProjectName,
    user: CurrentUser,
    x_sender: str | None = Header(None),
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

    # sanity check

    affected_entities: list[tuple[ProjectLevelEntityType, str]] = []
    for operation in payload.operations:
        if operation.type == "create":
            # create should be safe.
            # It will fail if the is provided and is already exists,
            # but it will fail gracefully. No need to check for duplicates.
            continue
        assert (
            operation.entity_id is not None
        ), "entity id is required for update/delete"
        key = (operation.entity_type, operation.entity_id)
        if key in affected_entities:
            raise BadRequestException(
                f"Duplicate operation for {operation.entity_type} {operation.entity_id}"
            )
        affected_entities.append(key)

    if payload.can_fail:
        events, response = await process_operations(
            project_name,
            user,
            payload.operations,
            can_fail=True,
        )
        return response

    # If can_fail is false, process all items in a transaction
    # and roll back on error

    events = []
    with suppress(RollbackException):
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                events, response = await process_operations(
                    project_name,
                    user,
                    payload.operations,
                    transaction=conn,
                )

                if not response.success:
                    events = []
                    raise RollbackException()

    for event in events:
        background_tasks.add_task(
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )

    return response
