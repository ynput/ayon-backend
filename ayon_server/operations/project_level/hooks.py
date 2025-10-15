from collections.abc import Awaitable, Callable, Iterable

from pydantic import BaseModel

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.logging import logger

from .models import OperationModel


class HookResult(BaseModel):
    on_result: list[str] | None = None


HookType = Callable[
    [OperationModel, ProjectLevelEntity, UserEntity | None], Awaitable[HookResult]
]


class OperationHooks:
    """Registry for operation hooks.

    Operation hook is an async function with the following signature:

    ```
    async def hook(
        operation: OperationModel,
        entity: ProjectLevelEntity,
        user: UserEntity | None,
    ) -> None:
        pass
    ```

    The hook is called BEFORE the operation is executed.

    The user argument is the user performing the operation,
    None if the operation is performed by the system.

    Entity is the entity on which the operation is performed.
    It is always a ProjectLevelEntity. In the case of create operation,
    it is a copy of the entity to be created.

    In the case of update operation, it is a copy of the entity
    before the update is applied.

    In both cases, hook should not modify the entity, but the operation data
    (operation.data) or raise exceptions to prevent the operation.
    """

    _hooks = []

    @classmethod
    def register(cls, hook: HookType) -> None:
        logger.debug(f"Registering operation hook: {hook}")
        cls._hooks.append(hook)

    @classmethod
    def hooks(cls) -> Iterable[HookType]:
        return cls._hooks
