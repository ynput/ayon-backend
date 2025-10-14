from typing import Any

from ayon_server.forms import SimpleForm

from .enum_item import EnumItem


class BaseEnumResolver:
    """Base class for enum resolvers."""

    name: str

    async def get_settings_form(self) -> SimpleForm | None:
        """Return a form for resolver settings.

        Settings are used to provide additional context to the resolver.
        """

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        """Resolve enum options based on the provided context."""
        return []
