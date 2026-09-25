import os

import yaml

from ayon_server.config import ayonconfig
from ayon_server.helpers.modules import import_module


def get_addon_from_dir(addon_dir: str) -> tuple[str, str]:
    """Return the addon name and version from the directory name"""
    package_path = os.path.join(addon_dir, "package.py")
    dirname = os.path.basename(addon_dir)
    metadata = {}
    if os.path.exists(package_path):
        package_module_name = f"{dirname}-package"
        package_module = import_module(package_module_name, package_path)
        for key in ("name", "version"):
            if hasattr(package_module, key):
                metadata[key] = getattr(package_module, key)

    elif os.path.exists(os.path.join(addon_dir, "package.yml")):
        with open(os.path.join(addon_dir, "package.yml")) as f:
            metadata = yaml.safe_load(f)

    elif os.path.exists(os.path.join(addon_dir, "package.yaml")):
        with open(os.path.join(addon_dir, "package.yaml")) as f:
            metadata = yaml.safe_load(f)

    if "name" in metadata and "version" in metadata:
        return metadata["name"], metadata["version"]
    raise ValueError(f"Addon {dirname} is missing name or version")


def get_downloaded_addons() -> list[tuple[str, str]]:
    """Return a list of all downloaded addons

    Returns a list of (addon_name, addon_version) tuples
    regardless they are active or not.
    """
    result = []
    for addon_name in os.listdir(ayonconfig.addons_dir):
        addon_dir = os.path.join(ayonconfig.addons_dir, addon_name)
        if not os.path.isdir(addon_dir):
            continue
        for addon_version in os.listdir(addon_dir):
            addon_version_dir = os.path.join(addon_dir, addon_version)
            if not os.path.isdir(addon_version_dir):
                continue
            try:
                result.append(get_addon_from_dir(addon_version_dir))
            except ValueError:
                pass

    return result
