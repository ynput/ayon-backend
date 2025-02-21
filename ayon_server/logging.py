__all__ = ["logging", "log_traceback", "critical_error"]

import sys
import time
import traceback

import loguru

from ayon_server.config import ayonconfig
from ayon_server.utils import indent, json_dumps


def write_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def serializer(message) -> None:
    record = message.record

    if ayonconfig.log_mode == "json":
        tr = {
            "file": record["file"].path,
            "line": record["line"],
            "function": record["function"],
        }
        simplified = {
            "timestamp": time.time(),
            "level": record["level"].name.lower(),
            "message": record["message"],
            **tr,
            **record["extra"],
        }
        serialized = json_dumps(simplified)
        write_stderr(serialized)

    else:
        level = record["level"].name
        message = record["message"]
        module = record["name"]
        formatted = f"{level:<8} | {module:<25} | {message}"
        write_stderr(formatted)
        if tb := record.get("traceback"):
            write_stderr(indent(str(tb)))


def get_logger():
    logger = loguru.logger
    logger.remove(0)
    logger.add(serializer, level=ayonconfig.log_level)
    return logger


logging = get_logger()


def log_traceback(message="Exception!", **kwargs):
    """Log the current exception traceback."""
    tb = traceback.format_exc()
    logging.error(message, traceback=tb, **kwargs)


def critical_error(message="Critical Error!", **kwargs):
    """Log a critical error message and exit the program."""
    logging.critical(message, **kwargs)
    logging.error("Exiting program.")
    sys.exit(1)
