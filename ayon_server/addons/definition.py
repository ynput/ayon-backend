import os
from typing import TYPE_CHECKING

import semver
import yaml

from ayon_server.addons.addon import METADATA_KEYS, BaseServerAddon
from ayon_server.config import ayonconfig
from ayon_server.helpers.modules import classes_from_module, import_module
from ayon_server.logging import log_traceback, logger
from ayon_server.utils import slugify

if TYPE_CHECKING:
    from ayon_server.addons.library import AddonLibrary


def _version_sort_key(v: str) -> semver.Version:
    # Semver first, but allow non-semver (legacy) versions as well
    try:
        return semver.Version.parse(v)
    except ValueError:
        return semver.Version(0, 0, 0, prerelease=slugify(v, separator=""))


def sorted_versions(versions) -> list[str]:
    try:
        return sorted(versions, key=_version_sort_key)
    except Exception:
        return sorted(versions)


class ServerAddonDefinition:
    title: str | None = None
    app_host_name: str | None = None

    def __init__(self, library: "AddonLibrary", addon_dir: str):
        self.library = library
        self.addon_dir = addon_dir
        self.restart_requested = False
        self._versions: dict[str, BaseServerAddon] | None = None

        if not self.versions:
            logger.warning(f"Addon {self.name} has no versions")
            return
        self._update_metadata()

    def _update_metadata(self) -> None:
        """Validate the loaded versions, take app host name and title from them"""
        self.app_host_name = None
        for version in self.versions.values():
            if self.app_host_name is None and version.app_host_name:
                self.app_host_name = version.app_host_name

            if version.name != self.name:
                raise ValueError(
                    f"Addon {self.name} has version {version.version} with "
                    f"mismatched name {version.name} != {self.name}"
                )

            self.title = version.title  # Use the latest title

    @property
    def project_can_override_addon_version(self) -> bool:
        """
        Returns true if the addon (at least one of its versions)
        allows version override per project (using project bundle)
        """
        return any(
            version.get_project_can_override_addon_version()
            for version in self.versions.values()
        )

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
        return f"[{self.dir_name.capitalize()}]"

    @property
    def versions(self) -> dict[str, BaseServerAddon]:
        """Return a list of addon versions.

        The list is a dictionary with version names as keys and addon
        instances as values. Addons are initialized when this property
        is accessed for the first time, which should happen
        right after server startup.
        """
        if self._versions is None:
            self._versions = {}
            for version_name in sorted_versions(os.listdir(self.addon_dir)):
                version_dir = os.path.join(self.addon_dir, version_name)
                try:
                    self._init_version_dir(version_dir)
                except AssertionError as e:
                    logger.error(f"Failed to initialize addon {version_dir}: {e}")
                except Exception:
                    log_traceback(f"Failed to initialize addon {version_dir}")

        return self._versions

    def _init_version_dir(
        self, version_dir: str, *, allow_legacy: bool = True
    ) -> BaseServerAddon | None:
        """Initialize one version directory, None if it is not an addon"""
        if os.path.exists(os.path.join(version_dir, "__init__.py")):
            assert allow_legacy, f"Legacy addon {version_dir} is not supported"
            return self.init_legacy_addon(version_dir)

        for filename in ["package.py", "package.yml", "package.yaml"]:
            if os.path.exists(os.path.join(version_dir, filename)):
                return self.init_addon(version_dir)
        return None

    def load_version(self, version_dir: str) -> BaseServerAddon:
        """Load a version added to the addon directory after startup.

        Idempotent: returns the version if it is already loaded.
        Legacy addons are not supported. Raises when it cannot be loaded.
        """
        for loaded in self.versions.values():
            if os.path.realpath(loaded.addon_dir) == os.path.realpath(version_dir):
                return loaded

        addon = self._init_version_dir(version_dir, allow_legacy=False)
        if addon is None:
            raise ValueError(f"{version_dir} is not an addon")

        versions = self.versions
        self._versions = {v: versions[v] for v in sorted_versions(versions)}
        try:
            self._update_metadata()
        except ValueError:
            self.unload_version(addon.version)
            raise
        return addon

    def init_addon(self, addon_dir: str) -> BaseServerAddon | None:
        """Initialize the addon using package.py/package.yml/package.yaml file.

        package file must contain at least name and version keys.
        additional metadata (title, services) are optional, may be as well
        defined in the addon class itself, but it is recommended to keep
        them in the package file for better readability and maintainability.
        """
        vname = slugify(f"{self.dir_name}-{os.path.split(addon_dir)[-1]}")

        server_module_path = os.path.join(addon_dir, "server", "__init__.py")
        package_path = os.path.join(addon_dir, "package.py")

        # addon metadata
        metadata = {}

        if os.path.exists(package_path):
            package_module_name = f"{vname}-package"
            package_module = import_module(package_module_name, package_path)
            for key in METADATA_KEYS:
                if hasattr(package_module, key):
                    metadata[key] = getattr(package_module, key)

        elif os.path.exists(os.path.join(addon_dir, "package.yml")):
            with open(os.path.join(addon_dir, "package.yml")) as f:
                metadata = yaml.safe_load(f)

        elif os.path.exists(os.path.join(addon_dir, "package.yaml")):
            with open(os.path.join(addon_dir, "package.yaml")) as f:
                metadata = yaml.safe_load(f)

        assert "name" in metadata, f"Addon {vname} is missing name"
        assert "version" in metadata, f"Addon {metadata['name']} is missing version"

        # when the addon directory is a git repository,
        # append -git to the version this is useful for development
        # the server-part of the addon directly from the git repository
        # on the server

        if ayonconfig.use_git_suffix_for_addons:
            if os.path.exists(os.path.join(addon_dir, ".git")):
                version = metadata["version"].split("-")[0]
                version = version.split("+")[0]
                version += "+git"
                metadata["version"] = version

        try:
            semver.Version.parse(metadata["version"])
        except ValueError:
            raise AssertionError(
                f"Addon {metadata['name']} has invalid version {metadata['version']}"
            )

        # Import the server module

        module = import_module(vname, server_module_path)

        # And initialize the addon

        if self._versions is None:
            self._versions = {}

        addon = None
        for Addon in classes_from_module(BaseServerAddon, module):
            addon = Addon(self, addon_dir=addon_dir, **metadata)
            if addon.restart_requested:
                logger.warning(
                    f"{addon} requested server restart during initialization."
                )
                self.restart_requested = True
            self._versions[metadata["version"]] = addon
        return addon

    def init_legacy_addon(self, addon_dir: str) -> BaseServerAddon | None:
        """Initialize old-style addon with __init__.py in the root directory.

        This style is deprecated and will be removed in the future.
        New style is supported since 1.0.3
        """

        mfile = os.path.join(addon_dir, "__init__.py")
        vname = slugify(f"{self.dir_name}-{os.path.split(addon_dir)[-1]}")
        module = import_module(vname, mfile)

        if self._versions is None:
            self._versions = {}

        addon = None
        for Addon in classes_from_module(BaseServerAddon, module):
            # legacy addons don't have metadata in the package file,
            # and they depend on class attributes.
            addon = Addon(self, addon_dir)
            addon.legacy = True
            if addon.restart_requested:
                logger.warning(
                    f"{addon} requested server restart during initialization."
                )
                self.restart_requested = True
            self._versions[Addon.version] = addon
        return addon

    @property
    def latest(self) -> BaseServerAddon | None:
        if not self.versions:
            return None
        versions = list(self.versions.keys())
        max_version = max(versions, key=semver.Version.parse)
        return self.versions[max_version]

    @property
    def is_system(self) -> bool:
        for version in self.versions.values():
            if version.system:
                return True
        return False

    @property
    def addon_type(self) -> str:
        sorted_versions = sorted(
            self.versions.values(),
            key=lambda x: semver.Version.parse(x.version),
        )
        if not sorted_versions:
            return "pipeline"
        return sorted_versions[-1].addon_type

    def __getitem__(self, item) -> BaseServerAddon:
        return self.versions[item]

    def get(self, item, default=None) -> BaseServerAddon | None:
        return self.versions.get(item, default)

    def unload_version(self, version: str) -> None:
        """Unload the given version of the addon."""
        if self._versions and version in self._versions:
            del self._versions[version]
