import asyncio
import os
from collections.abc import Generator

from ayon_server.exceptions import AyonException
from ayon_server.types import Platform
from ayon_server.utils.json import json_loads


def get_desktop_dir(*args: str, for_writing: bool = True) -> str:
    """Get path to desktop directory.
    If the directory does not exist, create it.
    args: path to the directory relative to the desktop directory
    """

    # TODO: Make this configurable
    root = "/storage/desktop"
    directory = os.path.join(root, *args)
    if not os.path.isdir(directory):
        if for_writing:
            try:
                os.makedirs(directory)
            except Exception as e:
                raise AyonException(f"Failed to create desktop directory: {e}")
    return directory


def iter_names(directory: str) -> Generator[str, None, None]:
    """Iterate over package names in a directory."""

    root = get_desktop_dir(directory, for_writing=False)
    if not os.path.isdir(root):
        return
    for filename in os.listdir(root):
        if not os.path.isfile(os.path.join(root, filename)):
            continue
        if not filename.endswith(".json"):
            continue
        yield filename[:-5]


def _list_dependency_packages() -> dict[Platform, list[str]]:
    """List all downloaded dependency packages."""

    desktop_dir = get_desktop_dir("dependency_packages", for_writing=False)

    result: dict[Platform, list[str]] = {
        "windows": [],
        "linux": [],
        "darwin": [],
    }
    for mname in iter_names("dependency_packages"):
        mpath = os.path.join(desktop_dir, mname + ".json")
        with open(mpath) as f:
            try:
                data = json_loads(f.read())
            except Exception:
                continue

        platform = data.get("platform")
        filename = data.get("filename")
        if platform and filename and platform in result:
            result[platform].append(filename)

    for platform in result:
        result[platform].sort(reverse=True)
    return result


async def list_dependency_packages() -> dict[Platform, list[str]]:
    """Async wrapper for listing dependency packages."""
    return await asyncio.to_thread(_list_dependency_packages)


def _list_installer_versions() -> list[str]:
    """List all downloaded launcher versions."""

    desktop_dir = get_desktop_dir("installers", for_writing=False)

    result = set()
    for mname in iter_names("installers"):
        mpath = os.path.join(desktop_dir, mname + ".json")
        with open(mpath) as f:
            try:
                data = json_loads(f.read())
            except Exception:
                continue

        version = data.get("version")
        if version:
            result.add(version)

    return sorted(result, reverse=True)


async def list_installer_versions() -> list[str]:
    """Async wrapper for listing installer versions."""
    return await asyncio.to_thread(_list_installer_versions)
