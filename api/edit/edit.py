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
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel, ProjectLevelEntityType
from openpype.utils import create_uuid

router = APIRouter(tags=["Edit"])

#
# Models
#

EditOperation = Literal["create", "update", "delete"]


class EditOperationModel(OPModel):
    id: str = Field(
        default_factory=create_uuid,
        description="ID of operation",
    )
    type: EditOperation = Field(
        ...,
        description="Type of operation",
    )
    entity_type: ProjectLevelEntityType = Field(
        ...,
        description="Type of the entity",
    )
    entity_id: str | None = Field(
        None,
        description="ID of the entity. None for create",
    )
    data: dict[str, Any] | None = Field(
        None,
        description="Data to be used for create or update",
    )


class EditRequestModel(OPModel):
    operations: list[EditOperationModel] = Field(default_factory=list)
    can_fail: bool = False


class EditItemResponseModel(OPModel):
    id: str = Field(..., title="Operation ID")
    success: bool = Field(..., title="Operation success")
    error: str | None = Field(None, title="Error message")
    # entity_id is optional for the cases create operation fails
    entity_id: str | None = Field(None, title="Entity ID")


class EditResponseModel(OPModel):
    operations: list[EditItemResponseModel] = Field(default_factory=list)
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
    operation: EditOperationModel,
    transaction=None,
) -> tuple[ProjectLevelEntity, EditItemResponseModel]:
    """Process a single operation. Raise exception on error."""

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
        entity.ensure_update_access(user)
        entity.patch(payload)
        await entity.save(transaction=transaction)
        print(f"updated {entity_class.__name__} {entity.id}")

    elif operation.type == "delete":
        entity = await entity_class.load(project_name, operation.entity_id)
        await entity.ensure_delete_access(user)
        await entity.delete(transaction=transaction)

    return entity, EditItemResponseModel(
        success=True, id=operation.id, entity_id=entity.id
    )


async def process_operations(
    project_name: str,
    user: UserEntity,
    operations: list[EditOperationModel],
    can_fail: bool = False,
    transaction=None,
) -> EditResponseModel:

    result: list[EditItemResponseModel] = []
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
        except Exception as exc:
            log_traceback()
            result.append(
                EditItemResponseModel(
                    success=False,
                    id=operation.id,
                    error=str(exc),
                )
            )
            if not can_fail:
                break

    success = all(op.success for op in result)

    if success or can_fail:
        for entity in to_commit:
            print("commiting", entity.entity_type, entity.id)
            await entity.commit(transaction=transaction)

    return EditResponseModel(operations=result, success=success)


#
# Edit request
#


@router.post("/projects/{project_name}/edit")
async def edit(
    payload: EditRequestModel,
    project_name: str = Depends(dep_project_name),
    user: UserEntity = Depends(dep_current_user),
):

    response = None
    if payload.can_fail:
        response = await process_operations(
            project_name,
            user,
            payload.operations,
            can_fail=True,
        )
    else:
        try:
            async with Postgres.acquire() as conn:
                async with conn.transaction():
                    response = await process_operations(
                        project_name,
                        user,
                        payload.operations,
                        transaction=conn,
                    )

                    if not response.success:
                        raise Exception(response.error)
        except Exception:
            print("Rollback!")

    return response
