import os

from nxtools import logging, slugify

from openpype.addons.utils import import_module


class ServerAddonDefinition:
    name: str
    title: str | None = None
    description: str = ""
    addon_type: str = "module"

    def __init__(self, library, addon_dir):
        self.library = library
        self.addon_dir = addon_dir
        self._versions = None

        assert hasattr(self, "name") and type(self.name) is str
        assert self.addon_type in ["host", "module"]

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
