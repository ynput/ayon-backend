"""
This module provides backwards compatibility for addons that rely
on the old nxtools module. It exports the same functions, reimplemented
in ayon_server.logging and ayon_server.utils

Eventually, this module will be deprecated and removed.
"""

__all__ = [
    "slugify",
    "indent",
    "logging",
    "log_traceback",
    "critical_error",
    "get_base_name",
]

from ayon_server.logging import critical_error, log_traceback
from ayon_server.logging import logger as logging
from ayon_server.utils.strings import get_base_name, indent, slugify
