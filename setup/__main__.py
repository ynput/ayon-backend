import asyncio
import sys
from typing import Any

import asyncpg
from nxtools import critical_error, log_traceback, logging

from openpype.lib.postgres import Postgres
from openpype.utils import json_loads
from setup.attributes import deploy_attributes
from setup.roles import deploy_roles
from setup.users import deploy_users

# Defaults which should allow OpenPype to run out of the box

DATA: dict[str, Any] = {
    "users": [
        {
            "name": "admin",
            "password": "admin",
            "fullName": "OpenPype admin",
            "isAdmin": True,
        },
        {
            "name": "manager",
            "password": "manager",
            "fullName": "OpenPype manager",
            "isManager": True,
        },
        {
            "name": "user",
            "password": "user",
            "fullName": "OpenPype user",
            "defaultRoles": ["viewer"]
        },
    ],
    "roles": [
        {
            "name": "viewer",
            "data": {
                "read": "all",
                "create": [],
                "update": [],
                "delete": [],
            },
        }
    ],
}


async def main() -> None:
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
            raw_data = sys.stdin.read()
            try:
                data: dict[str, Any] = json_loads(raw_data)
            except Exception:
                log_traceback()
                critical_error("Invalid setup fileprovided")

            DATA.update(data)
        else:
            logging.warning("No setup file provided. Using defaults")

        projects: list[str] = []
        async for row in Postgres.iterate("SELECT name FROM projects"):
            projects.append(row["name"])

        users: list[dict[str, Any]] = DATA["users"]
        roles: list[dict[str, Any]] = DATA.get("roles", [])

        await deploy_users(users, projects)
        await deploy_roles(roles)

    logging.goodnews("Setup is finished")


if __name__ == "__main__":
    asyncio.run(main())
