import os
from typing import Literal, Type, Any
from nxtools import logging, slugify
from openpype.addons.utils import import_module
from openpype.settings.common import BaseSettingsModel


class ServerAddonDefinition:
    name: str
    title: str | None = None
    description: str | None = None
    addon_type: Literal["host", "module"]

    def __init__(self, library, addon_dir):
        self.library = library
        self.addon_dir = addon_dir
        self._versions = None

    @property
    def friendly_name(self):
        return self.title or self.name

    @property
    def versions(self):
        if self._versions is None:
            self._versions = {}
            for version_name in os.listdir(self.addon_dir):
                mdir = os.path.join(self.addon_dir, version_name)
                mfile = os.path.join(mdir, "__init__.py")
                if not os.path.exists(os.path.join(mfile)):
                    continue

                vname = slugify(f"{self.name}-{version_name}")
                try:
                    addon = import_module(vname, mfile).AddOn
                except AttributeError:
                    logging.error(f"Addon {vname} is not valid")
                    continue
                self._versions[addon.version] = addon(self, mdir)

        return self._versions


class BaseServerAddon:
    version: str
    definition: ServerAddonDefinition
    settings: Type[BaseSettingsModel] | None = None

    def __init__(self, definition: ServerAddonDefinition, addon_dir: str):
        self.definition = definition
        self.addon_dir = addon_dir

    async def get_studio_settings(self) -> BaseSettingsModel:
        """Return the addon settings with the studio overrides.

        You shouldn't override this method, unless absolutely necessary.
        """

        # res = await Postgres.fetch("SELECT ")

        return self.settings()

    async def get_project_settings(self, project_name: str) -> BaseSettingsModel:
        """Return the addon settings with the studio and project overrides.

        You shouldn't override this method, unless absolutely necessary.
        """
        return self.settings()

    #
    # Overridable methods
    #

    async def get_default_settings(self) -> BaseSettingsModel:
        """Get the default addon settings.

        Override this method to return the default settings for the addon.
        By default it returns defaults from the addon's settings model, but
        if you need to use a complex model or force required fields, you should
        do something like: `return self.settings(**YOUR_ADDON_DEFAULTS)`.
        """

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
