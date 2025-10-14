from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.modules import classes_from_module, import_module

from .base_resolver import BaseEnumResolver
from .enum_item import EnumItem


class EnumResolver:
    resolvers: dict[str, BaseEnumResolver]

    def __init__(self) -> None:
        module_path = "ayon_server.enum.resolvers"
        module = import_module(module_path, f"{module_path}/__init__.py")
        resolver_classes = classes_from_module(BaseEnumResolver, module)

        self.resolvers = {}
        for resolver_class in resolver_classes:
            resolver = resolver_class()
            self.resolvers[resolver.name] = resolver

    def register(self, resolver: BaseEnumResolver) -> None:
        self.resolvers[resolver.name] = resolver

    def unregister(self, resolver_name: str) -> None:
        self.resolvers.pop(resolver_name, None)

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
