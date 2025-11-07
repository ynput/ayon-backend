import asyncio

import asyncpg

from ayon_server.activities import ActivityFeedEventHook
from ayon_server.enum import EnumRegistry
from ayon_server.events.default_hooks import DEFAULT_HOOKS
from ayon_server.events.eventstream import EventStream
from ayon_server.extensions import init_extensions
from ayon_server.helpers.project_list import build_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger


async def ayon_init(
    extensions: bool = True,
    enum_registry: bool = True,
):
    """Initialize ayon for use with server or stand-alone tools

    This connects to the database and installs the event hooks.
    """
    retry_interval = 2
    with logger.contextualize(nodb=True):
        while Postgres.pool is None:
            try:
                await Postgres.connect()
            except ConnectionRefusedError:
                logger.info("Waiting for PostgreSQL", nodb=True)
            except asyncpg.exceptions.CannotConnectNowError:
                logger.info("PostgreSQL is starting", nodb=True)
            except Exception as e:
                msg = " ".join([str(k) for k in e.args])
                logger.error(f"Unable to connect to the database ({msg})", nodb=True)

            else:  # Connection successful
                break

            logger.debug(f"Retrying in {retry_interval} seconds", nodb=True)
            await asyncio.sleep(retry_interval)

        while not Redis.connected:
            try:
                await Redis.connect()
            except ConnectionError:
                logger.info("Waiting for Redis", nodb=True)
            except Exception as e:
                msg = " ".join([str(k) for k in e.args])
                logger.error(f"Unable to connect to Redis ({msg})", nodb=True)
            else:
                break

            logger.debug(f"Retrying in {retry_interval} seconds", nodb=True)
            await asyncio.sleep(retry_interval)

    if extensions:
        await init_extensions()

    # Install default event hooks
    for topic, hook, all_nodes in DEFAULT_HOOKS:
        EventStream.subscribe(
            topic,
            hook,
            all_nodes=all_nodes,
        )

    if enum_registry:
        EnumRegistry.initialize()
    ActivityFeedEventHook.install(EventStream)
    await build_project_list()
