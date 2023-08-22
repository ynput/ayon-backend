import asyncio
import sys
from pathlib import Path
from typing import Any

import asyncpg
from nxtools import critical_error, log_traceback, logging

from ayon_server.config import ayonconfig
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import json_loads
from setup.attributes import deploy_attributes
from setup.roles import deploy_roles
from setup.users import deploy_users

# Defaults which should allow Ayon server to run out of the box

DATA: dict[str, Any] = {
    "addons": {},
    "settings": {},
    "users": [],
    "roles": [],
}

if ayonconfig.force_create_admin:
    DATA["users"] = [
        {
            "name": "admin",
            "password": "admin",
            "fullName": "Ayon admin",
            "isAdmin": True,
        },
    ]


async def wait_for_postgres() -> None:
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


async def main(force: bool | None = None) -> None:
    """Main entry point for setup."""

    logging.info("Starting setup")

    await wait_for_postgres()

    try:
        await Postgres.fetch("SELECT * FROM projects")
    except Exception:
        has_schema = False
        force_install = True
    else:
        # DB is okay, if we just checking the state,
        # do not force the setup
        has_schema = True
        if force is None:
            force_install = "--ensure-installed" not in sys.argv
        else:
            force_install = force

    if ("--with-schema" in sys.argv) or (not has_schema):
        logging.info("(re)creating database schema")

        schema = Path("schemas/schema.drop.sql").read_text()
        await Postgres.execute(schema)

    # inter-version updates
    schema = Path("schemas/schema.public.update.sql").read_text()
    await Postgres.execute(schema)

    schema = Path("schemas/schema.public.sql").read_text()
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

        for name, value in DATA.get("secrets", {}).items():
            await Postgres.execute(
                """
                INSERT INTO secrets (name, value)
                VALUES ($1, $2)
                ON CONFLICT (name) DO UPDATE SET value = $2
                """,
                name,
                value,
            )

    logging.goodnews("Setup is finished")


if __name__ == "__main__":
    asyncio.run(main())
