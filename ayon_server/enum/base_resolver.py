from typing import TYPE_CHECKING, Any

from ayon_server.forms import SimpleForm

from .enum_item import EnumItem

if TYPE_CHECKING:
    from .enum_registry import EnumRegistry


class BaseEnumResolver:
    """Base class for enum resolvers."""

    name: str

    def __init__(self, enum_registry: "type[EnumRegistry]") -> None:
        self.enum_registry = enum_registry

    async def get_accepted_params(self) -> dict[str, type]:
        """Return a dictionary of accepted parameters and their types."""
        return {}

    async def get_settings_form(self) -> SimpleForm | None:
        """Return a form for resolver settings.

        Settings are used to provide additional context to the resolver.
        """

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        """Resolve enum options based on the provided context."""
        return []
