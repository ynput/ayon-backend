import asyncio
import time
import queue

from typing import Any
from nxtools import logging

from openpype.background import BackgroundTask
from openpype.events import dispatch_event


def parse_log_message(message):
    """Convert nxtools log message to event system message."""
    topic = {
        0: "log.debug",
        1: "log.info",
        2: "log.warning",
        3: "log.error",
        4: "log.success",
    }[message["message_type"]]

    description = message["message"].splitlines()[0]
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


class LogCollector(BackgroundTask):
    def initialize(self):
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.msg_id = 0
        self.start_time = time.time()

    def __call__(self, **kwargs):
        # We need to add messages to the queue even if the
        # collector is not running to catch the messages
        # that are logged during the startup.
        if len(self.queue.queue) > 1000:
            print("Log collector queue is full")
            return
        self.queue.put(kwargs)

    async def process_message(self, record):
        self.msg_id += 1
        try:
            message = parse_log_message(record)
            await dispatch_event(
                message["topic"],
                sender=None,
                project=None,
                user=None,
                description=message["description"],
                summary=None,
                payload=message["payload"],
                finished=True,
                store=True,
            )
        except Exception:
            # This actually should not happen, but if it does,
            # we don't want to crash the whole application and
            # we don't want to log the exception using the logger,
            # since it failed in the first place.
            print("Unable to dispatch log message", message["description"])

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
            print("Processing remaining log messages", len(self.queue.queue))
            record = self.queue.get()
            await self.process_message(record)


log_collector = LogCollector()
logging.add_handler(log_collector)
logging.info("Log collector initialized", handlers=None)
