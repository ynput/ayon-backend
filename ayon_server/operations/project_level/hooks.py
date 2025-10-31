from collections.abc import Awaitable, Callable, Iterable

from pydantic import BaseModel

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.logging import logger
from ayon_server.utils.hashing import create_uuid

from .models import OperationModel


class HookResult(BaseModel):
    message: str | None = None
    triggers: list[str] | None = None


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
    ) -> HookResult:
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

    Handling Hook result is not yet implemented.
    """

    _hooks: dict[str, HookType] = {}

    @classmethod
    def register(cls, hook: HookType) -> str:
        # Get the function name for better logging
        hook_name = getattr(hook, "__name__", str(hook))
        logger.debug(f"Registering operation hook '{hook_name}'")
        token = create_uuid()
        cls._hooks[token] = hook
        return token

    @classmethod
    def unregister(cls, token: str) -> None:
        if token in cls._hooks:
            hook = cls._hooks.pop(token)
            hook_name = getattr(hook, "__name__", str(hook))
            logger.debug(f"Unregistered operation hook '{hook_name}'")
        else:
            logger.warning(f"Attempted to unregister unknown operation hook '{token}'")

    @classmethod
    def hooks(cls) -> Iterable[HookType]:
        return cls._hooks.values()
