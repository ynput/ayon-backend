from typing import TYPE_CHECKING, Any

from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.modules import classes_from_module, import_module
from ayon_server.logging import logger

from .base_resolver import BaseEnumResolver
from .enum_item import EnumItem

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity


class EnumRegistry:
    resolvers: dict[str, BaseEnumResolver] = {}

    @classmethod
    def initialize(cls):
        module_path = "ayon_server/enum/resolvers"
        module = import_module(module_path, f"{module_path}/__init__.py")
        resolver_classes = classes_from_module(BaseEnumResolver, module)

        cls.resolvers = {}
        for resolver_class in resolver_classes:
            cls.register(resolver_class)

    @classmethod
    def register(cls, resolver: type[BaseEnumResolver]) -> None:
        if resolver.name in cls.resolvers:
            msg = f"Replaced enum resolver '{resolver.name}'"
        else:
            msg = f"Registered enum resolver '{resolver.name}'"

        try:
            cls.resolvers[resolver.name] = resolver(cls)
        except Exception as e:
            logger.warning(f"Failed to register enum resolver '{resolver.name}': {e}")
        else:
            logger.debug(msg)

    @classmethod
    def unregister(cls, resolver_name: str) -> None:
        cls.resolvers.pop(resolver_name, None)

    @classmethod
    async def get_accepted_params(cls, enum_name: str) -> dict[str, type]:
        try:
            resolver = cls.resolvers[enum_name]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{enum_name}'")
        return await resolver.get_accepted_params()

    @classmethod
    async def resolve(
        cls,
        enum_name: str,
        *,
        context: dict[str, Any] | None = None,
        user: "UserEntity | None" = None,
    ) -> list[EnumItem]:
        try:
            resolver = cls.resolvers[enum_name]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{enum_name}'")

        context = context or {}
        if user is not None:
            context["user"] = user

        enum = await resolver.resolve(context)
        return enum
