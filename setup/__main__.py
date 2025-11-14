import asyncio
import sys
from pathlib import Path
from typing import Any

from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import critical_error, log_traceback, logger
from ayon_server.version import __version__ as server_version
from setup.access_groups import deploy_access_groups
from setup.attributes import deploy_attributes
from setup.database import db_migration
from setup.initial_bundle import create_initial_bundle
from setup.template import get_setup_template
from setup.users import deploy_users


async def main(force: bool | None = None) -> None:
    """Main entry point for setup."""

    logger.info("Starting setup")

    await ayon_init(extensions=False, enum_registry=False)

    try:
        await Postgres.fetch("SELECT * FROM projects")
    except Exception:
        logger.warning("Database is empty")
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
        logger.info("(re)creating database schema")

        schema = Path("schemas/schema.drop.sql").read_text()
        await Postgres.execute(schema)

    db_version = await db_migration(has_schema)

    schema = Path("schemas/schema.public.sql").read_text()
    await Postgres.execute(schema)

    # Save the current database version (latest migration applied)

    await Postgres.execute(
        """
        INSERT INTO config (key, value) VALUES ('dbVersion', $1)
        ON CONFLICT (key) DO UPDATE SET value = $1
        """,
        db_version,
    )

    # This is something we can do every time.
    # Similar to database migrations, built-in attributes
    # may change between versions, so we need to ensure
    # they are up-to-date, when the container is started.

    await deploy_attributes()

    # When the setup is started for the first time, or
    # is invoked using `make setup`, we  apply the
    # setup template.

    if force_install:
        template = await get_setup_template()

        projects: list[str] = []
        async for row in Postgres.iterate("SELECT name FROM projects"):
            projects.append(row["name"])

        users: list[dict[str, Any]] = template["users"]
        access_groups: list[dict[str, Any]] = template.get("accessGroups", [])

        await deploy_users(users, projects)
        await deploy_access_groups(access_groups)

        for name, value in template.get("secrets", {}).items():
            await Postgres.execute(
                """
                INSERT INTO secrets (name, value)
                VALUES ($1, $2)
                ON CONFLICT (name) DO UPDATE SET value = $2
                """,
                name,
                value,
            )

        for key, value in template.get("config", {}).items():
            await Postgres.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
                """,
                key,
                value,
            )

        if bundle_data := template.get("initialBundle"):
            if not isinstance(bundle_data, dict):
                logger.warning("Invalid initial bundle data")
            else:
                await create_initial_bundle(bundle_data)

    # If the server was updated to a new version,
    # save the current version in the database.

    await Postgres.execute(
        """
        INSERT INTO server_updates (version)
        VALUES ($1) ON CONFLICT (version) DO NOTHING
        """,
        server_version,
    )

    # Attributes may have changed, so we need to rebuild
    # existing hierarchies.

    from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes

    project_list = await get_project_list()
    for project in project_list:
        try:
            await rebuild_inherited_attributes(project.name)
        except Exception:
            log_traceback(
                f"Unable to rebuild attributes for {project.name}. "
                "Project may be corrupted."
            )

    logger.success("Setup is finished")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log_traceback()
        critical_error("Setup failed")
    sys.exit(0)
