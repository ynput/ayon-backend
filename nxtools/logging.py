__all__ = ["logging"]

import sys
import traceback

import loguru

from ayon_server.config import ayonconfig
from ayon_server.utils import json_dumps

from .string_utils import indent


def serializer(message: loguru.Message) -> None:
    record = message.record

    if ayonconfig.log_mode == "json":
        simplified = {
            "level": record["level"].name,
            "message": record["message"],
            **record["extra"],
        }
        serialized = json_dumps(simplified)
        print(serialized, file=sys.stderr, flush=True)

    else:
        print(message, file=sys.stderr, flush=True)
        if tb := record.get("traceback"):
            print(indent(str(tb)), file=sys.stderr)


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
