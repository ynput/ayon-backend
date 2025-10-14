from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.modules import classes_from_module, import_module
from ayon_server.logging import logger

from .base_resolver import BaseEnumResolver
from .enum_item import EnumItem


class EnumResolver:
    resolvers: dict[str, BaseEnumResolver]

    def __init__(self) -> None:
        module_path = "ayon_server/enum/resolvers"
        module = import_module(module_path, f"{module_path}/__init__.py")
        resolver_classes = classes_from_module(BaseEnumResolver, module)

        self.resolvers = {}
        for resolver_class in resolver_classes:
            self.register(resolver_class)

    def register(self, resolver: type[BaseEnumResolver]) -> None:
        self.resolvers[resolver.name] = resolver(self)
        logger.trace(f"Registered enum resolver '{resolver.name}'")

    def unregister(self, resolver_name: str) -> None:
        self.resolvers.pop(resolver_name, None)

    async def get_accepted_params(self, enum_name: str) -> dict[str, type]:
        try:
            resolver = self.resolvers[enum_name]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{enum_name}'")
        return await resolver.get_accepted_params()

    async def resolve(
        self,
        enum_name: str,
        *,
        context: dict[str, Any] | None = None,
        user: UserEntity | None = None,
    ) -> list[EnumItem]:
        try:
            resolver = self.resolvers[enum_name]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{enum_name}'")

        context = context or {}
        if user is not None:
            context["user"] = user

        enum = await resolver.resolve(context)
        return enum


enum_resolver = EnumResolver()
