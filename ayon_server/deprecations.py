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

from ayon_server.config import ayonconfig


class AyonDeprecationWarning(DeprecationWarning):
    """Deprecated AYON server API is used."""


@dataclass
class DeprecationRecord:
    category: str
    message: str
    path: str
    line: int
    count: int = 1


# Same candidates as AddonLibrary.get_addons_dir
_ADDONS_DIRS = tuple(
    f"{os.path.abspath(d)}/" for d in dict.fromkeys([ayonconfig.addons_dir, "addons"])
)

_records: dict[tuple[str, int, str, str], DeprecationRecord] = {}


def is_deprecation(category: type[Warning]) -> bool:
    # FastAPIDeprecationWarning is a subclass of UserWarning
    return issubclass(category, DeprecationWarning) or (
        "Deprecation" in category.__name__
    )


def is_addon_path(path: str) -> bool:
    return path.startswith(_ADDONS_DIRS)


def split_addon_path(path: str) -> tuple[str, str, str] | None:
    """Split an addon file path to addon dir, version dir and relative path.

    /addons/core/1.2.3/server/settings.py ->
        ("/addons/core", "1.2.3", "server/settings.py")
    """
    for addons_dir in _ADDONS_DIRS:
        if not path.startswith(addons_dir):
            continue
        parts = path.removeprefix(addons_dir).split("/", 2)
        if len(parts) < 3:
            return None
        return os.path.join(addons_dir, parts[0]), parts[1], parts[2]
    return None


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
