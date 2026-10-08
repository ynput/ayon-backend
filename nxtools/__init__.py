"""
This module provides backwards compatibility for addons that rely
on the old nxtools module. It exports the same functions, reimplemented
in ayon_server.logging and ayon_server.utils

The module is deprecated and will be removed. Each use of its members
is reported as a deprecation (see /api/system/deprecations) at the line
of the caller, so all addons importing it are tracked, not only the first one.
"""

import sys
import warnings
from typing import TYPE_CHECKING, Any

from ayon_server.deprecations import AyonDeprecationWarning

if TYPE_CHECKING:
    from ayon_server.logging import critical_error, log_traceback
    from ayon_server.logging import logger as logging
    from ayon_server.utils.strings import get_base_name, indent, slugify

__all__ = [
    "slugify",
    "indent",
    "logging",
    "log_traceback",
    "critical_error",
    "get_base_name",
]

# Exported name -> replacement (module, name)
_REPLACEMENTS: dict[str, tuple[str, str]] = {
    "slugify": ("ayon_server.utils.strings", "slugify"),
    "indent": ("ayon_server.utils.strings", "indent"),
    "get_base_name": ("ayon_server.utils.strings", "get_base_name"),
    "logging": ("ayon_server.logging", "logger"),
    "log_traceback": ("ayon_server.logging", "log_traceback"),
    "critical_error": ("ayon_server.logging", "critical_error"),
}


def __getattr__(name: str) -> Any:
    # Members are resolved lazily (instead of being imported at the module
    # level), so `from nxtools import ...` warns in every importing module.
    # A module level warning would be raised only by the first import.
    if name not in _REPLACEMENTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr = _REPLACEMENTS[name]
    # `from nxtools import x` checks the attribute in importlib first,
    # then reads it. Warn only once, when it is read.
    if not sys._getframe(1).f_code.co_filename.startswith("<frozen importlib"):
        warnings.warn(
            f"nxtools is deprecated, use `from {module_name} import {attr}` "
            f"instead of `from nxtools import {name}`",
            AyonDeprecationWarning,
            stacklevel=2,
        )
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)


def __dir__() -> list[str]:
    return list(__all__)
