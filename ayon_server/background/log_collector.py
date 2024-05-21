import asyncio
import queue
import time
from typing import Any

from ayon_server.background.background_worker import BackgroundWorker

# Fallback to the default logging module
# This is just used when ayon_server is loaded in order
# to get the version number.

try:
    from nxtools import logging

    has_nxtools = True
except ModuleNotFoundError:
    import logging  # type: ignore

    has_nxtools = False

else:
    from ayon_server.events import dispatch_event


def parse_log_message(message):
    """Convert nxtools log message to event system message."""
    message_type = message.get("message_type")
    if message_type is None or not isinstance(message_type, int):
        raise ValueError("Invalid log message type")
    topic = {
        0: "log.debug",
        1: "log.info",
        2: "log.warning",
        3: "log.error",
        4: "log.success",
    }[message["message_type"]]

    try:
        description = message["message"].splitlines()[0]
    except (IndexError, AttributeError):
        raise ValueError("Invalid log message")

    if len(description) > 100:
        description = description[:100] + "..."

    payload = {
        "message": message["message"],
    }

    return {
        "topic": topic,
        "description": description,
        "payload": payload,
    }


class LogCollector(BackgroundWorker):
    def initialize(self):
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.msg_id = 0
        self.start_time = time.time()

    def __call__(self, **kwargs):
        # We need to add messages to the queue even if the
        # collector is not running to catch the messages
        # that are logged during the startup.
        if kwargs["message_type"] == 0:
            return
        if len(self.queue.queue) > 1000:
            logging.warning("Log collector queue is full", handlers=None)
            return
        self.queue.put(kwargs)

    async def process_message(self, record):
        self.msg_id += 1
        try:
            message = parse_log_message(record)
        except ValueError:
            return

        try:
            await dispatch_event(
                message["topic"],
                # user=None, (TODO: implement this?)
                description=message["description"],
                payload=message["payload"],
            )
        except Exception:
            m = f"Unable to dispatch log message: {message['description']}"
            # do not use the logger, if you don't like recursion
            print(m, flush=True)

    async def run(self):
        # During the startup, we cannot write to the database
        # so the following loop patiently waits for the database
        # to be ready.
        while True:
            try:
                await dispatch_event("server.log_collector_started")
            except Exception:
                # Do not log the exception using the logger,
                # if you don't like recursion.
                await asyncio.sleep(0.5)
                continue
            break

        while True:
            if self.queue.empty():
                await asyncio.sleep(0.1)
                continue

            record = self.queue.get()
            await self.process_message(record)

    async def finalize(self):
        while not self.queue.empty():
            logging.debug(
                f"Processing {len(self.queue.queue)} remaining log messages",
                handlers=None,
            )
            record = self.queue.get()
            await self.process_message(record)


log_collector = LogCollector()

if has_nxtools:
    logging.add_handler(log_collector)
    logging.info("Log collector initialized", handlers=None)
