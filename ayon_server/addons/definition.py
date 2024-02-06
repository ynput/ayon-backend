import os
from typing import TYPE_CHECKING

import semver
import yaml
from nxtools import logging, slugify

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.utils import classes_from_module, import_module

if TYPE_CHECKING:
    from ayon_server.addons.library import AddonLibrary


class ServerAddonDefinition:
    title: str | None = None
    app_host_name: str | None = None

    def __init__(self, library: "AddonLibrary", addon_dir: str):
        self.library = library
        self.addon_dir = addon_dir
        self.restart_requested = False
        self._versions: dict[str, BaseServerAddon] | None = None

        if not self.versions:
            logging.warning(f"Addon {self.name} has no versions")
            return

        for version in self.versions.values():
            if self.app_host_name is None:
                self.app_host_name = version.app_host_name
            if self.name is None:
                self.name = version.name

            # do we need this check?
            if version.app_host_name != self.app_host_name:
                raise ValueError(
                    f"Addon {self.name} has version {version.version} with "
                    f"mismatched app host name {version.app_host_name} != {self.app_host_name}"
                )

            if version.name != self.name:
                raise ValueError(
                    f"Addon {self.name} has version {version.version} with "
                    f"mismatched name {version.name} != {self.name}"
                )

            self.title = version.title  # Use the latest title

    @property
    def dir_name(self) -> str:
        return os.path.split(self.addon_dir)[-1]

    @property
    def name(self) -> str:
        for version in self.versions.values():
            return version.name
        return os.path.split(self.addon_dir)[-1]

    @property
    def friendly_name(self) -> str:
        """Return a friendly (human readable) name of the addon."""
        if self.versions:
            if self.title:
                return self.title
            if hasattr(self, "name"):
                return self.name.capitalize()
        return f"(Empty addon {self.dir_name})"

    @property
    def versions(self) -> dict[str, BaseServerAddon]:
        if self._versions is None:
            self._versions = {}
            for version_name in os.listdir(self.addon_dir):
                version_dir = os.path.join(self.addon_dir, version_name)

                if os.path.exists(os.path.join(version_dir, "__init__.py")):
                    self.init_legacy_addon(version_dir)
                    continue

                if os.path.exists(os.path.join(version_dir, "package.py")):
                    self.init_addon(version_dir)
                    continue

                if os.path.exists(os.path.join(version_dir, "package.yml")):
                    self.init_addon(version_dir)
                    continue

                if os.path.exists(os.path.join(version_dir, "package.yaml")):
                    self.init_addon(version_dir)
                    continue

        return self._versions

    def init_addon(self, addon_dir: str):
        vname = slugify(f"{self.dir_name}-{os.path.split(addon_dir)[-1]}")

        server_module_path = os.path.join(addon_dir, "server", "__init__.py")

        addon_name: str | None = None
        addon_version: str | None = None

        package_path = os.path.join(addon_dir, "package.py")
        if os.path.exists(package_path):
            package_module_name = f"{vname}-package"

            try:
                package_module = import_module(package_module_name, package_path)
            except AttributeError:
                logging.error(f"Package {package_path} is not valid")
                return

            if not hasattr(package_module, "name"):
                logging.error(f"Package {package_path} is missing name")
                return

            if not hasattr(package_module, "version"):
                logging.error(f"Package {package_path} is missing version")
                return

            addon_name = package_module.name
            addon_version = package_module.version

        elif os.path.exists(os.path.join(addon_dir, "package.yml")):
            with open(os.path.join(addon_dir, "package.yml"), "r") as f:
                package = yaml.safe_load(f)
                addon_name = package.get("name")
                addon_version = package.get("version")

        elif os.path.exists(os.path.join(addon_dir, "package.yaml")):
            with open(os.path.join(addon_dir, "package.yaml"), "r") as f:
                package = yaml.safe_load(f)
                addon_name = package.get("name")
                addon_version = package.get("version")

        if not (addon_name and addon_version):
            logging.error(f"Addon {vname} is missing package information")
            return

        if os.path.exists(os.path.join(addon_dir, ".git")):
            if "+" in addon_version:
                addon_version += "-git"
            else:
                addon_version += "+git"

        try:
            module = import_module(vname, server_module_path)
        except AttributeError:
            logging.error(f"Addon {vname} is not valid")
            return

        for Addon in classes_from_module(BaseServerAddon, module):
            try:
                addon = Addon(
                    self,
                    addon_dir=addon_dir,
                    name=addon_name,
                    version=addon_version,
                )
            except ValueError:
                logging.error(
                    f"Error loading addon {addon_name} versions: {addon_version}"
                )
                return

            if addon.restart_requested:
                logging.warning(f"{addon}requested server restart")
                self.restart_requested = True

            self._versions[addon_version] = addon

    def init_legacy_addon(self, addon_dir: str):
        mfile = os.path.join(addon_dir, "__init__.py")
        vname = slugify(f"{self.dir_name}-{os.path.split(addon_dir)[-1]}")

        try:
            module = import_module(vname, mfile)
        except AttributeError:
            logging.error(f"Addon {vname} is not valid")
            return

        for Addon in classes_from_module(BaseServerAddon, module):
            try:
                self._versions[Addon.version] = Addon(self, addon_dir)
                self._versions[Addon.version].legacy = True
            except ValueError as e:
                logging.error(f"Error loading addon {vname} versions: {e.args[0]}")

            if self._versions[Addon.version].restart_requested:
                logging.warning(
                    f"Addon {self.name} version {Addon.version} "
                    "requested server restart"
                )
                self.restart_requested = True

    @property
    def latest(self) -> BaseServerAddon | None:
        if not self.versions:
            return None
        versions = list(self.versions.keys())
        max_version = max(versions, key=semver.VersionInfo.parse)
        return self.versions[max_version]

    @property
    def is_system(self) -> bool:
        for version in self.versions.values():
            if version.system:
                return True
        return False

    def __getitem__(self, item) -> BaseServerAddon:
        return self.versions[item]

    def get(self, item, default=None) -> BaseServerAddon | None:
        return self.versions.get(item, default)

    def unload_version(self, version: str) -> None:
        """Unload the given version of the addon."""
        if self._versions and version in self._versions:
            del self._versions[version]
