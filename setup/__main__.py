import asyncio
import os
import sys
from base64 import b64decode
from pathlib import Path
from typing import Any

from nxtools import critical_error, log_to_file, log_traceback, logging

from ayon_server.config import ayonconfig
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import json_loads
from setup.access_groups import deploy_access_groups
from setup.attributes import deploy_attributes
from setup.initial_bundle import create_initial_bundle
from setup.users import deploy_users

# Defaults which should allow Ayon server to run out of the box

DATA: dict[str, Any] = {
    "addons": {},
    "settings": {},
    "users": [],
    "roles": [],
    "config": {},
    "initialBundle": None,
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


async def main(force: bool | None = None) -> None:
    """Main entry point for setup."""

    logging.info("Starting setup")

    await ayon_init()

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

    if has_schema:
        # inter-version updates
        schema = Path("schemas/schema.public.update.sql").read_text()
        await Postgres.execute(schema)

    schema = Path("schemas/schema.public.sql").read_text()
    await Postgres.execute(schema)

    # This is something we can do every time.
    await deploy_attributes()

    TEMPLATE_ENV = "AYON_SETTINGS_TEMPLATE"

    if force_install:
        logging.info("Force install requested")
        template_data: dict[str, Any] = {}
        if "-" in sys.argv:
            logging.info("Reading setup file from stdin")
            raw_data = sys.stdin.read()
            try:
                template_data = json_loads(raw_data)
            except Exception:
                log_traceback()
                critical_error("Invalid setup file provided")

        elif os.path.exists("/template.json"):
            logging.info("Reading setup file from /template.json")
            try:
                raw_data = Path("/template.json").read_text()
                template_data = json_loads(raw_data)
            except Exception:
                logging.warning("Invalid setup file provided. Using defaults")
            else:
                logging.debug("Setting up from /template.json")
        elif raw_template_data := os.environ.get(TEMPLATE_ENV, ""):
            logging.info(f"Reading setup file from {TEMPLATE_ENV} env variable")
            try:
                template_data = json_loads(b64decode(raw_template_data).decode())
            except Exception:
                logging.warning(
                    f"Unable to parse {TEMPLATE_ENV} env variable. Using defaults"
                )
            else:
                logging.debug(f"Setting up from {TEMPLATE_ENV} env variable")
        else:
            logging.warning("No setup file provided. Using defaults")
        DATA.update(template_data)

        projects: list[str] = []
        async for row in Postgres.iterate("SELECT name FROM projects"):
            projects.append(row["name"])

        users: list[dict[str, Any]] = DATA["users"]
        access_groups: list[dict[str, Any]] = DATA.get("accessGroups", [])

        await deploy_users(users, projects)
        await deploy_access_groups(access_groups)

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

        for key, value in DATA.get("config", {}).items():
            await Postgres.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
                """,
                key,
                value,
            )

    if bundle_data := DATA.get("initialBundle"):
        if not isinstance(bundle_data, dict):
            logging.warning("Invalid initial bundle data")
        else:
            await create_initial_bundle(bundle_data)

    from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes

    project_list = await get_project_list()
    for project in project_list:
        await rebuild_inherited_attributes(project.name)

    logging.goodnews("Setup is finished")


if __name__ == "__main__":
    logging.user = "setup"
    if ayonconfig.log_file is not None:
        logging.add_handler(log_to_file(ayonconfig.log_file))
    asyncio.run(main())
