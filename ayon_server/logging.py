__all__ = ["logger", "log_traceback", "critical_error"]

import sys
import time
import traceback

from loguru import logger as loguru_logger

from ayon_server.config import ayonconfig
from ayon_server.utils import indent, json_dumps

CONTEXT_KEY_BLACKLIST = {"nodb", "traceback"}


def _write_stderr(message: str) -> None:
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


def log_traceback(message="Exception!", **kwargs):
    """Log the current exception traceback."""
    tb = traceback.format_exc()
    logger.error(message, traceback=tb, **kwargs)
    _write_stderr(indent(tb))


def critical_error(message="Critical Error!", **kwargs):
    """DEPRECATED: Log a critical error message and exit the program."""
    logger.critical(message, **kwargs)
    logger.error("Exiting program.")
    sys.exit(1)
