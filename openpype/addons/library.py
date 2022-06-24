import os

from typing import ItemsView
from nxtools import logging

from openpype.addons.addon import BaseServerAddon
from openpype.addons.definition import ServerAddonDefinition

# from openpype.addons.utils import classes_from_module, import_module
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres


class AddonLibrary:
    ADDONS_DIR = "addons"
    _instance = None

    @classmethod
    def getinstance(cls):
        if cls._instance is None:
            cls._instance = AddonLibrary()
        return cls._instance

    def __init__(self) -> None:
        self.data = {}
        for addon_name in os.listdir(self.ADDONS_DIR):
            addon_dir = os.path.join(self.ADDONS_DIR, addon_name)
            if not os.path.isdir(addon_dir):
                continue

            definition = ServerAddonDefinition(self, addon_dir)
            if not definition.versions:
                continue

            logging.info("Initializing addon", addon_name)
            self.data[addon_name] = definition

    @classmethod
    def addon(cls, name: str, version: str) -> BaseServerAddon:
        """Return an instance of the given addon.

        Raise NotFoundException if the addon is not found.
        """

        instance = cls.getinstance()
        if (definition := instance.get(name)) is None:
            raise NotFoundException(f"Addon {name} does not exist")
        if (addon := definition.versions.get(version)) is None:
            raise NotFoundException(f"Addon {name} version {version} does not exist")
        return addon

    def __getitem__(self, key) -> ServerAddonDefinition:
        return self.data[key]

    def __contains__(self, key) -> bool:
        return key in self.data

    def __iter__(self):
        return iter(self.data)

    def items(self) -> ItemsView[str, ServerAddonDefinition]:
        return self.data.items()

    def get(self, key: str, default=None) -> ServerAddonDefinition:
        return self.data.get(key, default)

    async def get_active_versions(self) -> dict[str, dict[str, str]]:
        active_versions = {}
        async for row in Postgres.iterate("SELECT * FROM addon_versions"):
            active_versions[row["name"]] = {
                "production": row["production_version"],
                "staging": row["staging_version"],
            }
        return active_versions

    async def get_production_addon(self, addon_name: str) -> BaseServerAddon | None:
        """Return a production instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        production_version = active_versions[addon_name]["production"]
        if production_version is None:
            return None
        return self[addon_name][production_version]

    async def get_staging_addon(self, addon_name: str) -> BaseServerAddon | None:
        """Return a staging instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        staging_version = active_versions[addon_name]["staging"]
        if staging_version is None:
            return None
        return self[addon_name][staging_version]
