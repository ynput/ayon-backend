from contextlib import suppress
from typing import Any, Literal

from fastapi import APIRouter, Depends
from nxtools import log_traceback

from openpype.api.dependencies import dep_current_user, dep_project_name
from openpype.entities import (
    FolderEntity,
    RepresentationEntity,
    SubsetEntity,
    TaskEntity,
    UserEntity,
    VersionEntity,
)
from openpype.entities.core import ProjectLevelEntity
from openpype.exceptions import OpenPypeException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel, ProjectLevelEntityType
from openpype.utils import create_uuid

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


class OperationsRequestModel(OPModel):
    operations: list[OperationModel] = Field(default_factory=list)
    can_fail: bool = False


class OperationResponseModel(OPModel):
    id: str = Field(..., title="Operation ID")
    type: OperationType = Field(..., title="Operation type")
    success: bool = Field(..., title="Operation success")
    error: str | None = Field(None, title="Error message")
    # entity_id is optional for the cases create operation fails
    entity_id: str | None = Field(None, title="Entity ID")


class OperationsResponseModel(OPModel):
    operations: list[OperationResponseModel] = Field(default_factory=list)
    success: bool = Field(..., title="Overall success")


#
# Processing
#


def get_entity_class(entity_type: ProjectLevelEntityType):
    return {
        "folder": FolderEntity,
        "task": TaskEntity,
        "subset": SubsetEntity,
        "version": VersionEntity,
        "representation": RepresentationEntity,
    }[entity_type]


async def process_operation(
    project_name: str,
    user: UserEntity,
    operation: OperationModel,
    transaction=None,
) -> tuple[ProjectLevelEntity, OperationResponseModel]:
    """Process a single operation. Raise an exception on error."""

    entity_class = get_entity_class(operation.entity_type)

    if operation.type == "create":
        payload = entity_class.model.post_model(**operation.data)
        payload_dict = payload.dict()
        if operation.entity_id is not None:
            payload_dict["id"] = operation.entity_id
        entity = entity_class(project_name, payload_dict)
        await entity.ensure_create_access(user)
        await entity.save(transaction=transaction)
        print(f"created {entity_class.__name__} {entity.id} {entity.name}")

    elif operation.type == "update":
        payload = entity_class.model.patch_model(**operation.data)
        entity = await entity_class.load(
            project_name,
            operation.entity_id,
            for_update=True,
            transaction=transaction,
        )
        await entity.ensure_update_access(user)
        entity.patch(payload)
        await entity.save(transaction=transaction)
        print(f"updated {entity_class.__name__} {entity.id}")

    elif operation.type == "delete":
        entity = await entity_class.load(project_name, operation.entity_id)
        await entity.ensure_delete_access(user)
        await entity.delete(transaction=transaction)

    return entity, OperationResponseModel(
        success=True,
        id=operation.id,
        type=operation.type,
        entity_id=entity.id,
    )


async def process_operations(
    project_name: str,
    user: UserEntity,
    operations: list[OperationModel],
    can_fail: bool = False,
    transaction=None,
) -> OperationsResponseModel:
    """Process a list of operations. Return a response model.

    This is separated from the endpoint so the endpoint can
    run this operation within or without a transaction context.

    This function shouldn't raise any exceptions, instead it should
    return a response model with success=False and error set.
    """

    result: list[OperationResponseModel] = []
    to_commit: list[ProjectLevelEntity] = []

    for i, operation in enumerate(operations):
        try:
            entity, response = await process_operation(
                project_name,
                user,
                operation,
                transaction=transaction,
            )
            result.append(response)
            if entity.entity_type not in [e.entity_type for e in to_commit]:
                to_commit.append(entity)
        except OpenPypeException as e:
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    error=e.detail,
                    entity_id=operation.entity_id,
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
                    error=str(exc),
                    entity_id=operation.entity_id,
                )
            )

            if not can_fail:
                # No need to continue
                break

    # Create overall success value
    success = all(op.success for op in result)
    if success or can_fail:
        for entity in to_commit:
            await entity.commit(transaction=transaction)

    return OperationsResponseModel(operations=result, success=success)


#
# Operations request
#


@router.post(
    "/projects/{project_name}/operations",
    response_model=OperationsResponseModel,
)
async def operations(
    payload: OperationsRequestModel,
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
):
    """
    Process multiple operations (create / update / delete) in a single request.

    All operations are processed in the order they are provided in the request.
    If can_fail is set to False, the processing stops on the first error and
    all previous operations are rolled back. If can_fail is set to True, the
    processing continues and all operations are committed.

    The response contains the list of operations with their success status.
    In case of failure, the error message is provided for each operation (TODO).

    The endpoint should never return an error status code - if so, something is
    very wrong (or the request is malformed).
    """

    if payload.can_fail:
        response = await process_operations(
            project_name,
            user,
            payload.operations,
            can_fail=True,
        )
        return response

    # If can_fail is false, process all items in a transaction
    # and roll back on error

    with suppress(RollbackException):
        async with Postgres.acquire() as conn:
            async with conn.transaction():
                response = await process_operations(
                    project_name,
                    user,
                    payload.operations,
                    transaction=conn,
                )

                if not response.success:
                    raise RollbackException()

    return response
