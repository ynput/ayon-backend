__all__ = ["logger", "log_traceback", "critical_error"]

import os
import sys
import time
import traceback
from typing import TypedDict

from loguru import logger as loguru_logger

from ayon_server.config import ayonconfig
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


class ExceptionInfo(TypedDict):
    status: int
    detail: str
    traceback: str | None


def log_exception(
    exc: BaseException,
    message: str | None = None,
    **kwargs,
) -> ExceptionInfo:
    """Log an exception with its traceback."""

    path_prefix = f"{os.getcwd()}/"
    formatted = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    formatted = formatted.replace("{", "{{").replace("}", "}}")
    tb = traceback.extract_tb(exc.__traceback__)
    traceback_msg = f"{formatted}\n\n"
    for frame in tb[-20:]:
        fpath = frame.filename.split("/")
        for p in ("starlette", "fastapi", "python3.11", "pydantic"):
            # Too noisy. ignore
            if p in fpath:
                break
        else:
            filepath = frame.filename.removeprefix(path_prefix)
            traceback_msg += f"{filepath}:{frame.lineno}\n"
            traceback_msg += f"{frame.line}\n\n"

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
