import os
from typing import Any, Literal, Type

from nxtools import logging, slugify

from openpype.addons.utils import import_module
from openpype.lib.postgres import Postgres
from openpype.settings.common import BaseSettingsModel


class BaseServerAddon:
    name: str
    description: str
    addon_type: Literal["host", "module"]

    def __init__(self, library, addon_dir):
        self.library = library
        self.addon_dir = addon_dir
        self._versions = None

        print(f"Initializing {self.name} in {self.addon_dir}")

    @property
    def versions(self):
        if self._versions is None:
            self._versions = {}
            for version_name in os.listdir(self.addon_dir):
                mfile = os.path.join(self.addon_dir, version_name, "__init__.py")
                if not os.path.exists(os.path.join(mfile)):
                    continue

                vname = slugify(f"{self.name}-{version_name}")
                try:
                    addon = import_module(vname, mfile).AddOn
                except AttributeError:
                    logging.error(f"Addon {vname} is not valid")
                    continue
                self._versions[addon.version] = addon(self)

        return self._versions


class BaseServerAddonVersion:
    version: str
    system_settings: Type[BaseSettingsModel] | None = None
    project_settings: Type[BaseSettingsModel] | None = None

    def __init__(self, group):
        self.group = group

    def convert_system_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        return overrides

    def convert_project_overrides(
        self,
        from_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        return overrides


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
