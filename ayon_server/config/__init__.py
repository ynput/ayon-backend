__all__ = ["ayonconfig", "get_addons_dir"]

import os

from .ayonconfig import ayonconfig


def get_addons_dir() -> str | None:
    """Return the directory, from which the addons are loaded."""
    for d in [ayonconfig.addons_dir, "addons"]:
        if not os.path.isdir(d):
            continue
        return d
    return None
