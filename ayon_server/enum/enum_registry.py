import inspect
from typing import TYPE_CHECKING, Annotated, Any

from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.modules import classes_from_module, import_module
from ayon_server.logging import logger
from ayon_server.types import AttributeType, Field, OPModel

from ..forms import SimpleFormField
from .base_resolver import BaseEnumResolver
from .enum_item import EnumItem

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity


class EnumResolverInfo(OPModel):
    name: Annotated[
        str,
        Field(
            title="Resolver name",
            example="statuses",
        ),
    ]
    label: Annotated[
        str,
        Field(
            title="Resolver label",
            description="Optional human-readable label for the resolver",
            example="Statuses",
        ),
    ]
    description: Annotated[
        str | None,
        Field(
            title="Resolver description",
            description="Optional human-readable description for the resolver",
            example="List of available statuses for tasks",
        ),
    ] = None
    accepted_params: Annotated[
        dict[str, AttributeType],
        Field(
            title="Accepted parameters",
            description="Dictionary of accepted query parameters and their type names",
            example={"project_name": "string", "include_root": "bool"},
        ),
    ]
    settings_form: Annotated[
        list[SimpleFormField] | None,
        Field(
            title="Settings form",
            description="Optional form fields for resolver settings",
        ),
    ] = None


reserved_params = {"project_name", "user"}


async def resolver_sanity_check(resolver: BaseEnumResolver) -> None:
    accepted_params = await resolver.get_accepted_params()
    if any(param in reserved_params for param in accepted_params):
        logger.warning(
            f"Resolver '{resolver.name}' uses reserved parameter names: "
            f"{reserved_params & set(accepted_params)}"
        )


class EnumRegistry:
    resolvers: dict[str, BaseEnumResolver] = {}

    @classmethod
    async def initialize(cls):
        module_path = "ayon_server/enum/resolvers"
        module = import_module(module_path, f"{module_path}/__init__.py")
        resolver_classes = classes_from_module(BaseEnumResolver, module)

        cls.resolvers = {}
        for resolver_class in resolver_classes:
            await cls.register(resolver_class)

    @classmethod
    async def register(cls, resolver: type[BaseEnumResolver]) -> None:
        if resolver.name in cls.resolvers:
            msg = f"Replaced enum resolver '{resolver.name}'"
        else:
            msg = f"Registered enum resolver '{resolver.name}'"

        try:
            resolver_instance = resolver(cls)
            await resolver_sanity_check(resolver_instance)
            cls.resolvers[resolver.name] = resolver_instance
        except Exception as e:
            logger.warning(f"Failed to register enum resolver '{resolver.name}': {e}")
        else:
            logger.debug(msg)

    @classmethod
    def unregister(cls, resolver_name: str) -> None:
        cls.resolvers.pop(resolver_name, None)

    @classmethod
    async def get_accepted_params(cls, enum_name: str) -> dict[str, AttributeType]:
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

    @classmethod
    async def list_resolvers(cls) -> list[EnumResolverInfo]:
        result = []
        for name, resolver in cls.resolvers.items():
            params = await resolver.get_accepted_params()
            settings_form = await resolver.get_settings_form()

            description = resolver.__doc__.strip() if resolver.__doc__ else None
            if description is not None:
                description = inspect.cleandoc(description)

            result.append(
                EnumResolverInfo(
                    name=name,
                    label=resolver.label or name,
                    description=description,
                    accepted_params=params,
                    settings_form=list(settings_form)
                    if settings_form is not None
                    else None,
                )
            )
        return sorted(result, key=lambda r: r.label.lower())
