from typing import TYPE_CHECKING, Any, Callable, Type

from openpype.lib.postgres import Postgres
from openpype.settings import BaseSettingsModel, apply_overrides

if TYPE_CHECKING:
    from openpype.addons.definition import ServerAddonDefinition


class BaseServerAddon:
    version: str
    definition: "ServerAddonDefinition"
    endpoints: list[dict[str, Any]]
    settings_model: Type[BaseSettingsModel] | None = None
    frontend_scopes: dict[str, Any] = {}
    frontend_dir: str = "frontend/dist"

    def __init__(self, definition: "ServerAddonDefinition", addon_dir: str):
        self.definition = definition
        self.addon_dir = addon_dir
        self.endpoints = []
        self.setup()

    def __repr__(self):
        return f"<Addon name='{self.definition.name}' version='{self.version}'>"

    @property
    def friendly_name(self) -> str:
        """Return the friendly name of the addon."""
        return f"{self.definition.friendly_name} {self.version}"

    def get_frontend_dir(self) -> str:
        return self.frontend_dir

    def get_settings_model(self) -> Type[BaseSettingsModel] | None:
        return self.settings_model

    #
    # Settings
    #

    async def get_studio_overrides(self) -> dict[str, Any]:
        """Load the studio overrides from the database."""

        res = await Postgres.fetch(
            f"""
            SELECT data FROM settings
            WHERE addon_name = '{self.definition.name}'
            AND addon_version = '{self.version}'
            ORDER BY snapshot_time DESC LIMIT 1
            """
        )
        if res:
            return res[0]["data"]
        return {}

    async def get_project_overrides(self, project_name: str) -> dict[str, Any]:
        """Load the project overrides from the database."""
        # TODO
        return {}

    async def get_studio_settings(self) -> BaseSettingsModel | None:
        """Return the addon settings with the studio overrides.

        You shouldn't override this method, unless absolutely necessary.
        """

        settings = await self.get_default_settings()
        if settings is None:
            return None
        overrides = await self.get_studio_overrides()
        if overrides:
            settings = apply_overrides(settings, overrides)

        return settings

    async def get_project_settings(self, project_name: str) -> BaseSettingsModel | None:
        """Return the addon settings with the studio and project overrides.

        You shouldn't override this method, unless absolutely necessary.
        """
        # TODO
        return await self.get_studio_settings()

    #
    # Overridable methods
    #

    async def get_default_settings(self) -> BaseSettingsModel | None:
        """Get the default addon settings.

        Override this method to return the default settings for the addon.
        By default it returns defaults from the addon's settings model, but
        if you need to use a complex model or force required fields, you should
        do something like: `return self.get_settings_model(**YOUR_ADDON_DEFAULTS)`.
        """

        if (model := self.get_settings_model()) is None:
            return None
        return model()

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

    def setup(self):
        """Setup the addon."""
        pass

    def add_endpoint(
        self,
        path: str,
        handler: Callable,
        *,
        method: str = "GET",
        name: str = None,
        description: str = None,
    ):
        """Add a REST endpoint to the server."""

        self.endpoints.append(
            {
                "name": name or handler.__name__,
                "path": path,
                "handler": handler,
                "method": method,
                "description": description or handler.__doc__ or "",
            }
        )
