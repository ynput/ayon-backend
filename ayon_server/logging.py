__all__ = ["logger", "log_traceback", "critical_error"]

import os
import sys
import sysconfig
import time
import traceback
import warnings
from types import FrameType
from typing import NotRequired, TypedDict

from loguru import logger as loguru_logger
from pydantic.warnings import PydanticDeprecationWarning

from ayon_server.config import ayonconfig
from ayon_server.deprecations import (
    is_addon_path,
    is_deprecation,
    record_deprecation,
)
from ayon_server.utils import indent, json_dumps

CONTEXT_KEY_BLACKLIST = {"nodb", "traceback"}


def _write_stderr(message: str) -> None:
    """Write a message to standard error with immediate flushing.

    Args:
        message (str): The message to be printed to stderr.
    """
    print(message, file=sys.stderr, flush=True)


def _serializer(message) -> None:
    record = message.record
    level = record["level"].name
    message = record["message"]
    module = record["extra"].pop("module", None) or record["name"]

    if ayonconfig.log_mode == "json":
        #
        # JSON mode logging
        #

        payload = {
            "timestamp": time.time(),
            "level": level.lower(),
            "message": message,
            "module": module,
            **record["extra"],
        }
        serialized = json_dumps(payload)
        _write_stderr(serialized)

    else:
        #
        # Text mode logging
        #

        module = module.replace("ayon_server.", "")
        formatted = f"{level:<7} {module:<26} | {message}"
        _write_stderr(formatted)

        # Format the message according to the log context setting
        traceback: str | None = None

        # Put the module name and extra context info in a separate block
        contextual_info = ""
        for k, v in record["extra"].items():
            if k == "traceback":
                traceback = v
                continue
            if k in CONTEXT_KEY_BLACKLIST:
                continue
            contextual_info += f"{k}: {v}\n"

        if ayonconfig.log_context and contextual_info:
            _write_stderr(indent(contextual_info.rstrip()))

        if traceback:
            # We always print the traceback if it exists
            _write_stderr(indent("traceback:", 4))
            _write_stderr(indent(traceback, 6))

        if traceback or (ayonconfig.log_context and contextual_info):
            # Empty line after contextual info / traceback
            _write_stderr("")


logger = loguru_logger.bind()
logger.remove(0)
logger.add(_serializer, level=ayonconfig.log_level)


#
# Python warnings
#
# Warnings (deprecations from Pydantic, FastAPI, AYON itself...) are
# routed to the AYON logger. The reported location is the first frame
# in AYON or addon code, so warnings raised deep inside libraries point
# to the line that needs to be fixed.
#
# Deprecations are collected in ayon_server.deprecations. The ones
# caused by addons are not logged at all.
#

_AYON_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

# Library paths, which are never reported as a warning location
_LIBRARY_PATHS = tuple(
    {sysconfig.get_path("stdlib"), sysconfig.get_path("platstdlib")} - {None}
)

# AYON modules, that only pass arguments to Pydantic / FastAPI
# or import addon modules. Warnings are reported at their caller.
_AYON_PLUMBING = {
    os.path.join(_AYON_SERVER_DIR, *path.split("/"))
    for path in (
        "logging.py",
        "helpers/modules.py",
        "models/metaclass.py",
        "models/rest_model.py",
        "settings/common.py",
        "settings/pydantic_compat.py",
        "settings/settings_field.py",
    )
}

_reported_warnings: set[tuple[str, int, str, str]] = set()


def _is_library_code(filename: str) -> bool:
    return (
        filename.startswith("<")  # <frozen importlib._bootstrap> etc.
        or "site-packages" in filename
        or "dist-packages" in filename
        or filename.startswith(_LIBRARY_PATHS)
        or filename in _AYON_PLUMBING
    )


def _warning_location(filename: str, lineno: int) -> tuple[str, int] | None:
    """Return the location of the code, which caused the warning.

    Returns None if the warning did not originate from AYON or addon code.
    """
    if not _is_library_code(filename):
        return filename, lineno

    frame: FrameType | None = sys._getframe(1)
    while frame is not None:
        if not _is_library_code(frame.f_code.co_filename):
            return frame.f_code.co_filename, frame.f_lineno
        frame = frame.f_back
    return None


def _log_warning(
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file=None,
    line: str | None = None,
) -> None:
    if isinstance(message, PydanticDeprecationWarning):
        # Without the "Deprecated in Pydantic V2.0..." suffix
        text = message.message
    else:
        text = str(message)

    location = _warning_location(filename, lineno)
    if location is None:
        # Only a library is to blame. Nothing we can fix
        path, lineno = filename, lineno
        log_method = logger.debug
    else:
        path, lineno = location
        log_method = logger.warning

    if location and is_deprecation(category):
        is_new = record_deprecation(category.__name__, text, path, lineno)
        if not is_new or is_addon_path(path):
            # Addon deprecations are only reported by /api/system/deprecations
            # to keep the log readable. Summary is logged by AddonLibrary.
            return
    else:
        key = (path, lineno, category.__name__, text)
        if key in _reported_warnings:
            return
        _reported_warnings.add(key)

    path = path.removeprefix(f"{os.getcwd()}/")
    text = f"{category.__name__}: {text} at {path}:{lineno}"
    log_method(
        text.replace("{", "{{").replace("}", "}}"),
        module="warnings",
    )


warnings.showwarning = _log_warning

if not sys.warnoptions:
    # Report each warning (including deprecations, which Python hides
    # by default) once per location, where it originates.
    # Duplicates are filtered in _log_warning.
    warnings.simplefilter("always")
    for category in (PendingDeprecationWarning, ImportWarning, ResourceWarning):
        warnings.filterwarnings("ignore", category=category)


class ExceptionInfo(TypedDict):
    status: int
    detail: str
    traceback: NotRequired[str | None]


def _format_exception_only(exc: BaseException) -> str:
    formatted = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return formatted.replace("{", "{{").replace("}", "}}")


def _format_traceback(exc: BaseException) -> str:
    path_prefix = f"{os.getcwd()}/"
    traceback_msg = f"{_format_exception_only(exc)}\n\n"
    for frame in traceback.extract_tb(exc.__traceback__)[-20:]:
        fpath = frame.filename.split("/")
        for p in ("starlette", "fastapi", "python3.11", "pydantic"):
            # Too noisy. ignore
            if p in fpath:
                break
        else:
            filepath = frame.filename.removeprefix(path_prefix)
            traceback_msg += f"{filepath}:{frame.lineno}\n"
            traceback_msg += f"{frame.line}\n\n"
    return traceback_msg.strip()


def log_exception(
    exc: BaseException,
    message: str | None = None,
    **kwargs,
) -> ExceptionInfo:
    """Log an exception with its traceback."""

    formatted = _format_exception_only(exc)
    traceback_msg = _format_traceback(exc)

    # Include chained exceptions, so the root cause is not lost when
    # an exception is raised while handling another one
    seen = {id(exc)}
    chained: BaseException | None = exc
    while chained is not None:
        if chained.__cause__ is not None:
            chained, label = chained.__cause__, "Caused by"
        elif chained.__context__ is not None and not chained.__suppress_context__:
            chained, label = chained.__context__, "During handling of"
        else:
            break
        if id(chained) in seen:
            break
        seen.add(id(chained))
        traceback_msg += f"\n\n{label}:\n\n{_format_traceback(chained)}"

    if message is None:
        message = f"Unhandled exception: {formatted}"

    extras = kwargs.copy()
    extras["traceback"] = traceback_msg.strip()

    logger.error(message, **extras)

    return {
        "status": 500,
        "detail": formatted,
        "traceback": traceback_msg.strip(),
    }


def log_traceback(message: str | None = None, **kwargs) -> ExceptionInfo:
    """Log the current exception."""
    exc = sys.exc_info()[1]
    if not exc:
        raise RuntimeError("No exception to log")
    return log_exception(exc, message=message, **kwargs)


def critical_error(message="Critical Error!", **kwargs):
    """DEPRECATED: Log a critical error message and exit the program."""
    logger.critical(message, **kwargs)
    logger.error("Exiting program.")
    sys.exit(1)
