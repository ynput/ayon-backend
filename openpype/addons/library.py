import os
from nxtools import logging

from openpype.addons.addon import BaseServerAddon
from openpype.addons.utils import import_module
from openpype.lib.postgres import Postgres


class AddonLibrary:
    ADDONS_DIR = "addons"
    _instance = None

    @classmethod
    def getinstance(cls):
        if cls._instance is None:
            cls._instance = AddonLibrary()
        return cls._instance

    def __init__(self):
        self.data = {}
        for addon_name in os.listdir(self.ADDONS_DIR):
            addon_dir = os.path.join(self.ADDONS_DIR, addon_name)
            mfile = os.path.join(addon_dir, "__init__.py")

            if not os.path.isfile(mfile):
                continue

            try:
                AddOn = import_module(addon_name, mfile).ServerAddon
            except AttributeError:
                logging.error(f"Addon {addon_name} is not valid")
                continue

            self.data[AddOn.name] = AddOn(self, addon_dir)

    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, key):
        return key in self.data

    def __iter__(self):
        return iter(self.data)

    def items(self):
        return self.data.items()

    def get(self, key, default=None):
        return self.data.get(key, default)

    async def get_active_versions(self):
        active_versions = {}
        async for row in Postgres.iterate("SELECT * FROM addon_versions"):
            active_versions[row["name"]] = {
                "production": row["production_version"],
                "staging": row["staging_version"],
            }
        return active_versions

    async def get_production_addon(self, addon_name: str) -> BaseServerAddon:
        """Return a production instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        production_version = active_versions[addon_name]["production"]
        if production_version is None:
            return None
        return self[addon_name][production_version]

    async def get_staging_addon(self, addon_name: str) -> BaseServerAddon:
        """Return a staging instance of the addon."""
        active_versions = await self.get_active_versions()
        if addon_name not in active_versions:
            return None
        staging_version = active_versions[addon_name]["staging"]
        if staging_version is None:
            return None
        return self[addon_name][staging_version]
