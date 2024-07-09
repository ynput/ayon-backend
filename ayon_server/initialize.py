import asyncio

from nxtools import logging

from ayon_server.activities import ActivityFeedEventHook
from ayon_server.events import EventStream
from ayon_server.lib.postgres import Postgres


async def ayon_init():
    """Initialize ayon for use with server or stand-alone tools

    This connects to the database and installs the event hooks.
    """
    retry_interval = 5

    while True:
        try:
            await Postgres.connect()
        except Exception as e:
            msg = " ".join([str(k) for k in e.args])
            logging.error(f"Unable to connect to the database ({msg})", handlers=None)
            logging.info(f"Retrying in {retry_interval} seconds", handlers=None)
            await asyncio.sleep(retry_interval)
        else:
            break

    ActivityFeedEventHook.install(EventStream)
