"""Registry of deprecated features used by the server and addons.

Deprecation warnings raised by addon code (using the Pydantic 1 API,
deprecated FastAPI arguments, deprecated AYON arguments...) are not
logged individually, but collected here and exposed using
the /api/system/deprecations endpoint.

The registry is per process (worker). Addons are imported during
the server startup, so all workers collect the same deprecations.
"""

import os
from dataclasses import dataclass

from ayon_server.config import get_addons_dir


class AyonDeprecationWarning(DeprecationWarning):
    """Deprecated AYON server API is used."""


@dataclass
class DeprecationRecord:
    category: str
    message: str
    path: str
    line: int
    count: int = 1


_addons_dir: str | None = None


def _get_addons_dir() -> str | None:
    """Return the addons directory with a trailing slash"""
    global _addons_dir
    if _addons_dir is None and (addons_dir := get_addons_dir()):
        # Cached only once it exists
        _addons_dir = os.path.join(os.path.abspath(addons_dir), "")
    return _addons_dir


_records: dict[tuple[str, int, str, str], DeprecationRecord] = {}


def is_deprecation(category: type[Warning], message: str) -> bool:
    if issubclass(category, DeprecationWarning):
        return True
    if "Deprecation" in category.__name__:
        # FastAPIDeprecationWarning is a subclass of UserWarning
        return True
    # Pydantic 1 API removed in Pydantic 2 (such as model config keys)
    # is reported as UserWarning
    return "changed in V2" in message


def split_addon_path(path: str) -> tuple[str, str, str] | None:
    """Split an addon file path to addon dir, version dir and relative path.

    /addons/core/1.2.3/server/settings.py ->
        ("/addons/core", "1.2.3", "server/settings.py")

    Return None if the path is not a file of an addon.
    """
    addons_dir = _get_addons_dir()
    if addons_dir is None or not path.startswith(addons_dir):
        return None
    parts = path.removeprefix(addons_dir).split("/", 2)
    if len(parts) < 3:
        return None
    return os.path.join(addons_dir, parts[0]), parts[1], parts[2]


def is_addon_path(path: str) -> bool:
    return split_addon_path(path) is not None


def record_deprecation(category: str, message: str, path: str, line: int) -> bool:
    """Record a deprecation. Return True if it was not recorded before."""
    key = (path, line, category, message)
    if record := _records.get(key):
        record.count += 1
        return False
    _records[key] = DeprecationRecord(category, message, path, line)
    return True


def get_deprecations() -> list[DeprecationRecord]:
    return list(_records.values())
