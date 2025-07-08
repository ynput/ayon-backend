__all__ = [
    "ProjectLevelOperations",
    "OperationModel",
    "OperationResponseModel",
    "OperationsResponseModel",
]

import asyncio
import random
from typing import Any

from asyncpg.exceptions import IntegrityConstraintViolationError
from pydantic.error_wrappers import ValidationError

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.events import EventStream
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ConflictException,
    ServiceUnavailableException,
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.postgres_exceptions import parse_postgres_exception
from ayon_server.logging import log_traceback, logger
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid

from ..common import OperationType, RollbackException
from .entity_create import create_project_level_entity
from .entity_delete import delete_project_level_entity
from .entity_update import update_project_level_entity
from .models import OperationModel, OperationResponseModel, OperationsResponseModel


async def _process_operation(
    project_name: str,
    user: UserEntity | None,
    operation: OperationModel,
) -> tuple[ProjectLevelEntity, list[dict[str, Any]] | None, OperationResponseModel]:
    """Process a single operation. Raise an exception on error."""

    entity_class = get_entity_class(operation.entity_type)

    # Data for the event triggered after successful operation
    events: list[dict[str, Any]] | None = None
    status = 200

    if operation.type == "create":
        entity, events, status = await create_project_level_entity(
            entity_class,
            project_name,
            operation,
            user,
        )

    elif operation.type == "update":
        entity, events, status = await update_project_level_entity(
            entity_class,
            project_name,
            operation,
            user,
        )

    elif operation.type == "delete":
        entity, events, status = await delete_project_level_entity(
            entity_class,
            project_name,
            operation,
            user,
        )

    else:
        # This should never happen (already validated)
        raise BadRequestException(f"Unknown operation type {operation.type}")

    return (
        entity,
        events,
        OperationResponseModel(
            id=operation.id,
            type=operation.type,
            entity_id=entity.id,
            entity_type=operation.entity_type,
            success=True,
            status=status,
        ),
    )


async def _process_operations(
    project_name: str,
    operations: list[OperationModel],
    user_map: dict[str, UserEntity | None],
    *,
    can_fail: bool = False,
    raise_on_error: bool = True,
) -> tuple[list[dict[str, Any]], OperationsResponseModel]:
    """Process a list of operations.

    This function should not raise an exception. If an operation
    fails, success=False is returned.

    Returns a tuple of:
     - list of events to dispatch
     - list of operation responses

    """

    result: list[OperationResponseModel] = []
    to_commit: list[ProjectLevelEntity] = []
    events: list[dict[str, Any]] = []

    logger.debug(f"Processing {len(operations)} project {project_name} operations")
    for operation in operations:
        if operation.as_user:
            user = user_map.get(operation.as_user)
        else:
            user = None

        addr = f"{project_name}/{operation.entity_id}"
        op_tag = f"[{operation.entity_type.upper()} {operation.type.upper()}]"
        logger.debug(
            f"{op_tag} {addr}",
            project=project_name,
            operation_id=operation.id,
        )

        try:
            # This is a neat trick. transaction() will try
            # to reuse the current transaction if it exists,
            # but create a new one if it doesn't.

            # This way, every operation is ensured to run in a transaction,
            # but main process may wrap everything in a single one
            # to commit all operations at once.

            async with Postgres.transaction():
                entity, evt, response = await _process_operation(
                    project_name,
                    user,
                    operation,
                )
                if evt is not None:
                    events.extend(evt)
                result.append(response)
                if entity.entity_type not in [e.entity_type for e in to_commit]:
                    to_commit.append(entity)

        except ServiceUnavailableException as e:
            logger.debug(f"{e}, retrying operation")
            raise e

        except AyonException as e:
            logger.debug(
                f"{op_tag} failed: {e.detail}",
                project=project_name,
                operation_id=operation.id,
            )
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=e.status,
                    detail=e.detail,
                    error_code=e.code,
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )
            if not can_fail:
                if raise_on_error:
                    raise e
                break

        except ValidationError as e:
            logger.debug(
                f"{op_tag} failed: {e}",
                project=project_name,
                operation_id=operation.id,
            )
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=400,
                    detail=f"Invalid data provided: {e}",
                    error_code="invalid_data",
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )
            if not can_fail:
                if raise_on_error:
                    raise e
                break

        except IntegrityConstraintViolationError as e:
            parsed = parse_postgres_exception(e)
            logger.debug(
                f"{op_tag} failed: {parsed['detail']}",
                project=project_name,
                operation_id=operation.id,
            )
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=parsed["code"],
                    detail=parsed["detail"],
                    error_code=parsed.get("error"),
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )

            if not can_fail:
                if raise_on_error:
                    raise ConflictException(parsed["detail"])
                break

        except Exception as e:
            log_traceback(f"{op_tag} Unhandled exception")
            result.append(
                OperationResponseModel(
                    success=False,
                    id=operation.id,
                    type=operation.type,
                    status=500,
                    detail=str(e),
                    entity_id=operation.entity_id,
                    entity_type=operation.entity_type,
                )
            )

            if not can_fail:
                if raise_on_error:
                    raise e
                break

    # Create overall success value
    success = all(op.success for op in result)
    if success or can_fail:
        for e in to_commit:
            await e.commit()

    return events, OperationsResponseModel(operations=result, success=success)


class ProjectLevelOperations:
    def __init__(
        self,
        project_name: str,
        *,
        user: UserEntity | None = None,
        sender: str | None = None,
        sender_type: str | None = None,
    ) -> None:
        self.user = user
        self.sender = sender
        self.sender_type = sender_type
        self.project_name = project_name
        self.operations: list[OperationModel] = []
        self.user_entities_map: dict[str, UserEntity | None] = {}

    def append(self, operation: OperationModel) -> None:
        """Append an operation to the list.

        This method is used internally or if you
        already have an OperationModel instance.
        """

        if operation.as_user:
            uname = operation.as_user
            if uname not in self.user_entities_map:
                self.user_entities_map[uname] = None
        elif self.user:
            uname = self.user.name
        else:
            uname = None

        assert isinstance(operation, OperationModel)
        operation.as_user = uname
        self.operations.append(operation)

    def add(
        self,
        operation_type: OperationType,
        entity_type: ProjectLevelEntityType,
        *,
        entity_id: str | None = None,
        as_user: str | UserEntity | None = None,
        operation_id: str | None = None,
        force: bool = False,
        **kwargs,
    ) -> None:
        if isinstance(as_user, UserEntity):
            self.user_entities_map[as_user.name] = as_user
            uname = as_user.name
        elif as_user:
            uname = as_user
        else:
            uname = None

        self.append(
            OperationModel(
                id=operation_id or create_uuid(),
                type=operation_type,
                entity_type=entity_type,
                entity_id=entity_id,
                as_user=uname,
                force=force,
                data=kwargs,
            )
        )

    def create(
        self,
        entity_type: ProjectLevelEntityType,
        entity_id: str | None = None,
        *,
        as_user: str | UserEntity | None = None,
        **kwargs,
    ) -> None:
        """Create a project level entity."""
        self.add(
            "create",
            entity_type,
            entity_id=entity_id,
            as_user=as_user,
            **kwargs,
        )

    def update(
        self,
        entity_type: ProjectLevelEntityType,
        entity_id: str,
        *,
        as_user: str | UserEntity | None = None,
        **kwargs,
    ) -> None:
        """Update a project level entity."""
        self.add(
            "update",
            entity_type,
            entity_id=entity_id,
            as_user=as_user,
            **kwargs,
        )

    def delete(
        self,
        entity_type: ProjectLevelEntityType,
        entity_id: str,
        *,
        as_user: str | UserEntity | None = None,
        force: bool = False,
    ) -> None:
        """Delete a project level entity."""
        self.add(
            "delete",
            entity_type,
            entity_id=entity_id,
            as_user=as_user,
            force=force,
        )

    # Cross-validation

    def _validate(self) -> None:
        """Run sanity checks on the operations list."""

        affected_entities: list[tuple[ProjectLevelEntityType, str]] = []
        for operation in self.operations:
            if operation.type == "create":
                # create should be safe.
                # It will fail if the is provided and is already exists,
                # but it will fail gracefully. No need to check for duplicates.
                continue

            if not operation.entity_id:
                raise BadRequestException("entity_id is required for update/delete")

            key = (operation.entity_type, operation.entity_id)
            if key in affected_entities:
                raise BadRequestException(
                    "Duplicate operation for "
                    f"{operation.entity_type} {operation.entity_id}"
                )
            affected_entities.append(key)

    # Processing

    async def _process(
        self,
        can_fail: bool = False,
        raise_on_error: bool = True,
    ) -> OperationsResponseModel:
        self._validate()

        events: list[dict[str, Any]] = []
        response: OperationsResponseModel = OperationsResponseModel(
            operations=[], success=False
        )  # keep the type checker happy

        # Load user entities that we will use for operaratins to
        # check access permissions and to dispatch events
        if self.user:
            self.user_entities_map[self.user.name] = self.user
        for uname in self.user_entities_map:
            if not self.user_entities_map[uname]:
                self.user_entities_map[uname] = await UserEntity.load(uname)

        if can_fail:
            events, response = await _process_operations(
                self.project_name,
                self.operations,
                user_map=self.user_entities_map,
                can_fail=True,
                raise_on_error=False,
            )

        else:
            for _ in range(3):
                try:
                    async with Postgres.transaction():
                        events, response = await _process_operations(
                            self.project_name,
                            self.operations,
                            user_map=self.user_entities_map,
                            raise_on_error=raise_on_error,
                        )
                    if not response.success:
                        events = []
                        # Raise rollback exception to roll back the transaction
                        # but silence it so the response is returned
                        raise RollbackException()

                except RollbackException:
                    logger.trace("Operations rolled back")
                    break

                except ServiceUnavailableException:
                    # entity is locked by another operation,
                    # we will retry a few times
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    continue

                break
            else:
                raise ConflictException("Entity is locked by another operation")

        for event in events:
            await EventStream.dispatch(
                sender=self.sender,
                sender_type=self.sender_type,
                **event,
            )

        # TODO: remove this?
        # This is duplicate! It is handled by calling commit() on the entity
        # if "folder" in [r.entity_type for r in self.operations]:
        #     # Rebuild the hierarchy cache for folders
        #     await rebuild_hierarchy_cache(self.project_name)
        #     await rebuild_inherited_attributes(self.project_name)

        return response

    async def process(
        self,
        can_fail: bool = False,
        raise_on_error: bool = True,
    ) -> OperationsResponseModel:
        """
        Process the enqueued operations.

        raise_on_error is ignored if can_fail is True, when set to False,
        the function will return the response even if there are errors (success=False).
        When raise_on_error is True, the function will raise an exception when the first
        error is encountered, and the response will not be returned.

        Warning: Method can still raise BadRequestException even if can_fail is True or
        raise_on_error is False, if the request is invalid
        (e.g. missing entity_id for update)
        """

        try:
            return await self._process(can_fail=can_fail, raise_on_error=raise_on_error)
        finally:
            self.operations = []
