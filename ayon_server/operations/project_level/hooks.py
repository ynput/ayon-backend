from collections.abc import Awaitable, Callable, Iterable

from ayon_server.entities import UserEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.logging import logger

from .models import OperationModel

HookType = Callable[
    [str, OperationModel, ProjectLevelEntity, UserEntity | None], Awaitable[None]
]


class OperationHooks:
    """Registry for operation hooks.

    Operation hook is an async function with the following signature:
    async def hook(
        project_name: str,
        operation: OperationModel,
        entity: ProjectLevelEntity,
        user: UserEntity | None,
    ) -> None:

    The hook is called BEFORE the operation is executed.
    The user is the user performing the operation, None if the operation is
    performed by the system.

    Hooks are called in the order they are registered.
    They can modify the operation data or raise exceptions to prevent
    the operation from being executed. They should not modify the entity!
    """

    _hooks = []

    @classmethod
    def register(cls, hook: HookType) -> None:
        logger.debug(f"Registering operation hook: {hook}")
        cls._hooks.append(hook)

    @classmethod
    def hooks(cls) -> Iterable[HookType]:
        return cls._hooks
