import os
from typing import TYPE_CHECKING

from nxtools import logging, slugify

from openpype.addons.addon import BaseServerAddon
from openpype.addons.utils import classes_from_module, import_module

if TYPE_CHECKING:
    from openpype.addons.library import AddonLibrary


class ServerAddonDefinition:
    title: str | None = None
    addon_type: str | None = None

    def __init__(self, library: "AddonLibrary", addon_dir: str):
        self.library = library
        self.addon_dir = addon_dir
        self._versions: dict[str, BaseServerAddon] | None = None

        if not self.versions:
            logging.warning(f"Addon {self.name} has no versions")
            return

        for version in self.versions.values():
            if self.addon_type is None:
                self.addon_type = version.addon_type
            if self.name is None:
                self.name = version.name

            if version.addon_type != self.addon_type:
                raise ValueError(
                    f"Addon {self.name} has version {version.version} with "
                    f"mismatched type {version.addon_type} != {self.addon_type}"
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

        return self._versions

    def __getitem__(self, item) -> BaseServerAddon:
        return self.versions[item]
