import asyncio
import os
from urllib.parse import urlparse

import aiofiles
from fastapi import BackgroundTasks, Query, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EntityIdResponse
from ayon_server.config import ayonconfig
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import (
    ForbiddenException,
)
from ayon_server.helpers.project_list import build_project_list
from ayon_server.logging import logger
from setup.database import db_migration

from .router import router


def get_pg_connection() -> tuple[str, str, str, int, str]:
    conn_string = ayonconfig.postgres_url
    result = urlparse(conn_string)
    # Extract the relevant components
    user = result.username
    password = result.password
    host = result.hostname
    port = result.port or 5432
    database = result.path[1:]  # Remove the leading '/'
    assert (
        user and password and host and database and port
    ), "Postgres connection string is not valid"

    return user, password, host, port, database


async def import_database_file(
    dump_path: str,
    *,
    event_id: str,
    run_migration: bool = False,
):
    try:
        await update_event(
            event_id=event_id,
            description="Importing project...",
            status="in_progress",
        )

        if not os.path.exists(dump_path):
            logger.error("Dump file not found")
            await update_event(
                event_id=event_id,
                status="failed",
                description="Dump file not found",
            )
            return

        pg_user, pg_password, pg_host, pg_port, pg_database = get_pg_connection()

        env = os.environ.copy()
        env["PGPASSWORD"] = pg_password
        cmd = f"psql -h {pg_host} -U {pg_user} {pg_database} < {dump_path}"

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=None,
            stderr=None,
            env=env,
        )

        await process.communicate()

        if process.returncode == 0:
            await update_event(
                event_id=event_id,
                description="Project imported",
                status="finished",
            )

        else:
            await update_event(
                event_id=event_id,
                status="failed",
                description="Failed to import project",
            )

        if run_migration:
            # You should always run migration after importing a project
            await db_migration()

        # Rebuild project list. It's not costly and in most cases, it's useful
        await build_project_list()

    finally:
        if os.path.exists(dump_path):
            try:
                os.remove(dump_path)
            except Exception as e:
                logger.error(f"Failed to remove dump file: {e}")


@router.post("/dbimport", include_in_schema=False)
async def import_database(
    user: CurrentUser,
    request: Request,
    background_tasks: BackgroundTasks,
    run_db_migration: bool = Query(
        False,
        description="Run database migration after import",
    ),
) -> EntityIdResponse:
    """Apply a database file to the database.

    This endpoint is used for initialization of the database
    remotely and should not be used in production. Do not use
    if you are not sure what you are doing.
    """
    if not user.is_service:
        raise ForbiddenException()

    temp_file = "/storage/dbimport.sql"

    # Store file

    async with aiofiles.open(temp_file, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)

    event_id = await dispatch_event(
        "project_import",
        user=user.name,
        description="Importing project...",
    )

    background_tasks.add_task(
        import_database_file,
        temp_file,
        event_id=event_id,
        run_migration=run_db_migration,
    )
    return EntityIdResponse(id=event_id)
