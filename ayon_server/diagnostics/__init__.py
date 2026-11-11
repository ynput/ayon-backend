"""Read-only diagnostic checks of the server's dependencies.

Checks register themselves on import: import component modules here.
"""

__all__ = [
    "CODES",
    "CodeInfo",
    "Finding",
    "diagnostic_check",
    "register_code",
    "run_checks",
]

from . import postgres  # noqa: F401
from .checks import CODES, diagnostic_check, register_code, run_checks
from .models import CodeInfo, Finding

_ = [postgres]
