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
        key = enum_name.split(".")[0]
        try:
            resolver = cls.resolvers[key]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{key}'")
        return await resolver.get_accepted_params()

    @classmethod
    async def resolve(
        cls,
        enum_name: str,
        *,
        user: "UserEntity | None" = None,
        **context: Any,
    ) -> list[EnumItem]:
        if "." in enum_name:
            key, name = enum_name.split(".", 1)
        else:
            key, name = enum_name, None

        try:
            resolver = cls.resolvers[key]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{key}'")

        context = context or {}
        if user is not None:
            context["user"] = user
        if name is not None:
            context["name"] = name

        enum = await resolver.resolve(context)
        return enum

    @classmethod
    async def create_item(
        cls,
        enum_name: str,
        item: EnumItem,
        project_name: str | None = None,
        **kwargs,
    ) -> None:
        """Create a new enum item using the appropriate resolver.

        Args:
            enum_name: The name of the enum (e.g., "statuses", "folderTypes")
            item: The EnumItem to create
            project_name: Optional project name for project-specific enums

        Returns:
            The value of the created item

        Raises:
            BadRequestException: If the resolver is not found
            NotImplementedError: If the resolver doesn't support item creation
        """
        key = enum_name.split(".")[0]
        try:
            resolver = cls.resolvers[key]
        except KeyError:
            raise BadRequestException(f"Unknown enum resolver '{key}'")

        await resolver.create_item(item, project_name, **kwargs)
