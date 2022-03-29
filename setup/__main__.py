import asyncio
import sys

import asyncpg
from nxtools import critical_error, log_traceback, logging

from openpype.lib.postgres import Postgres
from openpype.utils import json_loads

from .attributes import deploy_attributes
from .roles import deploy_roles
from .users import deploy_users

# Defaults which should allow OpenPype to run out of the box

DATA = {
    "default_roles": {"viewer": "all"},
    "users": [
        {
            "name": "admin",
            "password": "admin",
            "fullname": "OpenPype admin",
            "roles": {
                "admin": True,
            },
        },
        {
            "name": "manager",
            "password": "manager",
            "fullname": "OpenPype manager",
            "roles": {
                "manager": True,
            },
        },
        {
            "name": "user",
            "password": "user",
            "fullname": "OpenPype user",
        },
    ],
    "roles": [{"name": "viewer", "data": {"read": "all"}}],
}


async def main():
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

    try:
        await Postgres.fetch("SELECT * FROM projects")
    except Exception:
        has_schema = False
        force_install = True
    else:
        # DB is okay, if we just checking the state,
        # do not force the setup
        has_schema = True
        force_install = "--ensure-installed" not in sys.argv

    if ("--with-schema" in sys.argv) or (not has_schema):
        logging.info("(re)creating database schema")
        schema = None

        with open("schemas/schema.drop.sql", "r") as f:
            schema = f.read()
        await Postgres.execute(schema)

        with open("schemas/schema.public.sql", "r") as f:
            schema = f.read()
        await Postgres.execute(schema)

    # This is something we can do every time.
    await deploy_attributes()

    if force_install:
        if "-" in sys.argv:
            data = sys.stdin.read()
            try:
                data = json_loads(data)
            except Exception:
                log_traceback()
                critical_error("Invalid setup fileprovided")

            DATA.update(data)
        else:
            logging.warning("No setup file provided. Using defaults")

        await deploy_users(DATA["users"], DATA["default_roles"])
        await deploy_roles(DATA.get("roles", {}))

    logging.goodnews("Setup is finished")


if __name__ == "__main__":
    asyncio.run(main())
