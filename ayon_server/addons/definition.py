import os
from typing import TYPE_CHECKING

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
        raise ValueError("No versions found")

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
                mdir = os.path.join(self.addon_dir, version_name)
                mfile = os.path.join(mdir, "__init__.py")
                if not os.path.exists(os.path.join(mfile)):
                    continue

                vname = slugify(f"{self.dir_name}-{version_name}")
                try:
                    module = import_module(vname, mfile)
                except AttributeError:
                    logging.error(f"Addon {vname} is not valid")
                    continue

                for Addon in classes_from_module(BaseServerAddon, module):
                    try:
                        self._versions[Addon.version] = Addon(self, mdir)
                    except ValueError as e:
                        logging.error(
                            f"Error loading addon {vname} versions: {e.args[0]}"
                        )

                    if self._versions[Addon.version].restart_requested:
                        logging.warning(
                            f"Addon {self.name} version {Addon.version} "
                            "requested server restart"
                        )
                        self.restart_requested = True

        return self._versions

    def __getitem__(self, item) -> BaseServerAddon:
        return self.versions[item]

    def get(self, item, default=None) -> BaseServerAddon | None:
        return self.versions.get(item, default)

    def unload_version(self, version: str) -> None:
        """Unload the given version of the addon."""
        if version not in self.versions:
            return None
        del self._versions[version]
