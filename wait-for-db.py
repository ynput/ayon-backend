#!/usr/bin/env python3

import asyncio
import asyncpg

from openpype.lib.postgres import Postgres
from nxtools import logging, log_traceback


async def wait_for_db() -> None:
    while 1:
        try:
            await Postgres.connect()
        except ConnectionRefusedError:
            logging.info("Waiting for PostgreSQL")
        except asyncpg.exceptions.CannotConnectNowError:
            logging.info("PostgreSQL is starting")
        except Exception:
            log_traceback()
        else:
            break
        await asyncio.sleep(1)

    while 1:
        try:
            await Postgres.fetch("SELECT * FROM projects")
        except Exception:
            log_traceback()
        else:
            break

        logging.info("Waiting for SQL schema")
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(wait_for_db())
