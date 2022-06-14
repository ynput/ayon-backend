from typing import TYPE_CHECKING, Any, Type

from openpype.settings.common import BaseSettingsModel

if TYPE_CHECKING:
    from openpype.addons.definition import ServerAddonDefinition


class BaseServerAddon:
    version: str
    definition: "ServerAddonDefinition"
    settings: Type[BaseSettingsModel] | None = None

    def __init__(self, definition: "ServerAddonDefinition", addon_dir: str):
        self.definition = definition
        self.addon_dir = addon_dir

    async def get_studio_settings(self) -> BaseSettingsModel | None:
        """Return the addon settings with the studio overrides.

        You shouldn't override this method, unless absolutely necessary.
        """

        # res = await Postgres.fetch("SELECT ")
        if self.settings is None:
            return None
        return self.settings()

    async def get_project_settings(self, project_name: str) -> BaseSettingsModel | None:
        """Return the addon settings with the studio and project overrides.

        You shouldn't override this method, unless absolutely necessary.
        """
        if self.settings is None:
            return None
        return self.settings()

    #
    # Overridable methods
    #

    async def get_default_settings(self) -> BaseSettingsModel | None:
        """Get the default addon settings.

        Override this method to return the default settings for the addon.
        By default it returns defaults from the addon's settings model, but
        if you need to use a complex model or force required fields, you should
        do something like: `return self.settings(**YOUR_ADDON_DEFAULTS)`.
        """

        if self.settings is None:
            return None
        return self.settings()

    def convert_system_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert system overrides from a previous version."""
        return overrides

    def convert_project_overrides(
        self,
        from_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert project overrides from a previous version."""
        return overrides
