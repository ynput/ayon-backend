import os
from typing import TYPE_CHECKING

from nxtools import logging, slugify

from openpype.addons.addon import BaseServerAddon
from openpype.addons.utils import classes_from_module, import_module

if TYPE_CHECKING:
    from openpype.addons.library import AddonLibrary


class ServerAddonDefinition:
    name: str
    title: str | None = None
    addon_type: str = "module"

    def __init__(self, library: "AddonLibrary", addon_dir: str):
        self.library = library
        self.addon_dir = addon_dir
        self._versions: dict[str, BaseServerAddon] | None = None

        assert hasattr(self, "name") and type(self.name) is str
        assert self.addon_type in ["host", "module"]

    @property
    def friendly_name(self) -> str:
        """Return a friendly (human readable) name of the addon."""
        return self.title or self.name.capitalize()

    @property
    def versions(self) -> dict[str, BaseServerAddon]:
        if self._versions is None:
            self._versions = {}
            for version_name in os.listdir(self.addon_dir):
                mdir = os.path.join(self.addon_dir, version_name)
                mfile = os.path.join(mdir, "__init__.py")
                if not os.path.exists(os.path.join(mfile)):
                    continue

                vname = slugify(f"{self.name}-{version_name}")
                try:
                    module = import_module(vname, mfile)
                except AttributeError:
                    logging.error(f"Addon {vname} is not valid")
                    continue

                for Addon in classes_from_module(BaseServerAddon, module):
                    self._versions[Addon.version] = Addon(self, mdir)

        return self._versions

    def __getitem__(self, item):
        return self.versions[item]
