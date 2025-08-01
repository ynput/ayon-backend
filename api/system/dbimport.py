import asyncio
import os
from typing import Annotated

import aiofiles
from fastapi import BackgroundTasks, Query, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EntityIdResponse
from ayon_server.events import dispatch_event, update_event
from ayon_server.exceptions import (
    ForbiddenException,
    ServiceUnavailableException,
)
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import build_project_list
from ayon_server.lib.postgres import Postgres, get_pg_connection_info
from ayon_server.logging import logger
from setup.database import db_migration

from .router import router

_lock = asyncio.Lock()


async def import_database_file(
    dump_path: str,
    *,
    event_id: str,
    run_migration: bool = False,
    single_transaction: bool = True,
    reload_projects: list[str] | None = None,
) -> None:
    """Import a database file into the PostgreSQL database.

    This function is intended to be run in the background after
    receiving a database dump file. It will execute the SQL commands
    in the dump file against the PostgreSQL database specified in
    the configuration.
    """

    all_ok = False

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

        conn_info = get_pg_connection_info()

        cmd = [
            "psql",
            "-h",
            conn_info["host"],
            "-U",
            conn_info["user"],
            "-d",
            conn_info["database"],
            "-f",
            dump_path,
        ]

        if single_transaction:
            cmd.append("--single-transaction")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=None,
            stderr=None,
            env={
                "PGPASSWORD": conn_info["password"],
                **os.environ,
            },
        )

        await process.communicate()

        if process.returncode == 0:
            await update_event(
                event_id=event_id,
                description="Database import completed successfully",
                status="finished",
            )

        if run_migration:
            # You should always run migration after importing a project
            await db_migration()

        # Rebuild project list. It's not costly and in most cases, it's useful
        await build_project_list()
        if reload_projects:
            # Reload specific projects
            for project_name in reload_projects:
                await rebuild_inherited_attributes(project_name)
                await rebuild_hierarchy_cache(project_name)

        all_ok = True

    finally:
        if os.path.exists(dump_path):
            try:
                os.remove(dump_path)
            except Exception as e:
                logger.error(f"Failed to remove dump file: {e}")

        if not all_ok:
            await update_event(
                event_id=event_id,
                status="failed",
                description="Failed to import database file",
            )


async def ensure_not_running() -> None:
    """Ensure that another import is not already running."""

    query = """
        SELECT id FROM events WHERE topic = 'database_import'
        AND status = 'in_progress'
        AND created_at > NOW() - INTERVAL '1 hour'
        LIMIT 1;
    """
    res = await Postgres.fetchrow(query)
    if res:
        raise ServiceUnavailableException(
            "Database import is already in progress. Please wait until it finishes."
        )


@router.post("/dbimport", include_in_schema=False)
async def import_database(
    user: CurrentUser,
    request: Request,
    background_tasks: BackgroundTasks,
    run_db_migration: Annotated[
        bool,
        Query(
            description="Run database migration after import",
        ),
    ] = False,
    single_transaction: Annotated[
        bool,
        Query(
            description="Run import in a single transaction",
        ),
    ] = True,
    reload_projects: Annotated[
        str | None,
        Query(
            description="Comma-separated list of projects to reload after import",
        ),
    ] = None,
) -> EntityIdResponse:
    """Apply a database file to the database.

    This endpoint is used for initialization of the database
    remotely and should not be used in production. Do not use
    if you are not sure what you are doing.
    """
    if not user.is_service:
        raise ForbiddenException()

    async with _lock:
        await ensure_not_running()

        temp_file = "/storage/dbimport.sql"
        upload_ok = False

        try:
            async with aiofiles.open(temp_file, "wb") as f:
                async for chunk in request.stream():
                    await f.write(chunk)
            upload_ok = True
        finally:
            if not upload_ok:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        logger.error(f"Failed to remove temp file: {e}")

        event_id = await dispatch_event(
            "database_import",
            user=user.name,
            description="Importing database file...",
        )

        reload_projects_list = []
        if reload_projects:
            reload_projects_list = [
                p.strip() for p in reload_projects.split(",") if p.strip()
            ]

        background_tasks.add_task(
            import_database_file,
            temp_file,
            event_id=event_id,
            run_migration=run_db_migration,
            single_transaction=single_transaction,
            reload_projects=reload_projects_list,
        )
        return EntityIdResponse(id=event_id)
