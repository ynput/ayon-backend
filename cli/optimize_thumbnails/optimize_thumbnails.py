import asyncio
import time

from ayon_server.cli import app
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_list
from ayon_server.helpers.thumbnails import (
    ThumbnailProcessNoop,
    process_thumbnail,
)
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.utils import format_filesize

MAX_THUMBNAIL_HEIGHT = 600
MAX_THUMBNAIL_WIDTH = 600


async def process_project_thumbnails(project_name: str) -> None:
    logger.info(f"Optimizing thumbnails for project: {project_name}")

    q = f"""
        WITH used_thumbnails AS (
            SELECT thumbnail_id id FROM project_{project_name}.folders
            WHERE thumbnail_id IS NOT NULL
            UNION
            SELECT thumbnail_id id FROM project_{project_name}.tasks
            WHERE thumbnail_id IS NOT NULL
            UNION
            SELECT thumbnail_id id FROM project_{project_name}.versions
            WHERE thumbnail_id IS NOT NULL
            UNION
            SELECT thumbnail_id id FROM project_{project_name}.workfiles
            WHERE thumbnail_id IS NOT NULL
        )

        SELECT id, mime, data FROM project_{project_name}.thumbnails
        WHERE meta = '{{}}'
        AND id IN (SELECT id FROM used_thumbnails)
        LIMIT 10
        """

    while True:
        count = 0
        async for row in Postgres.iterate(q):
            count += 1
            await asyncio.sleep(0.1)
            logger.debug(f"Processing thumbnail {row['id']} in {project_name}")

            mime = row["mime"]
            thumbnail_id = row["id"]
            payload = row["data"]

            try:
                thumbnail = await process_thumbnail(
                    payload,
                    (MAX_THUMBNAIL_WIDTH, MAX_THUMBNAIL_HEIGHT),
                    raise_on_noop=True,
                )
            except ThumbnailProcessNoop:
                thumbnail = payload
            else:
                storage = await Storages.project(project_name)
                await storage.store_thumbnail(thumbnail_id, payload)

            meta = {
                "originalSize": len(payload),
                "thumbnailSize": len(thumbnail),
                "mime": mime,
            }

            await Postgres.execute(
                f"""
                UPDATE project_{project_name}.thumbnails
                SET data = $1, meta = $2
                WHERE id = $3
                """,
                thumbnail,
                meta,
                thumbnail_id,
            )

        if count == 0:
            break


async def get_schema_size(project_name: str) -> int:
    q = """
        SELECT
            nspname AS schema_name,
            SUM(pg_total_relation_size(pg_class.oid)) AS schema_size
        FROM pg_class
        JOIN pg_namespace ON pg_class.relnamespace = pg_namespace.oid
        WHERE pg_namespace.nspname = $1
        GROUP BY nspname
    """

    r = await Postgres.fetch(q, f"project_{project_name}")
    try:
        return int(r[0]["schema_size"])
    except IndexError:
        return 0


@app.command()
async def optimize_thumbnails(
    project_name: str | None = None,
    vacuum: bool = True,
) -> None:
    """Optimize thumbnails for a project or all projects.

    Reduce the size of thumbnails stored in the database and
    offload them to the project storage.
    """

    await ayon_init()

    projects = await get_project_list()
    db_sizes: dict[str, int] = {}

    start_time = time.monotonic()
    if project_name is None:
        for project in projects:
            db_sizes[project.name] = await get_schema_size(project.name)
            await process_project_thumbnails(project.name)
    else:
        db_sizes[project_name] = await get_schema_size(project_name)
        await process_project_thumbnails(project_name)
    elapsed_time = time.monotonic() - start_time

    logger.info(f"Took {elapsed_time:.2f} seconds to optimize thumbnails")

    if vacuum:
        logger.info(
            "Vacuuming the database to reclaim space..." " This may take a while."
        )

        start_time = time.monotonic()
        await Postgres.execute("VACUUM FULL")
        elapsed_time = time.monotonic() - start_time
        logger.info(f"Took {elapsed_time:.2f} seconds to vacuum database")

        total_reduced_size = 0
        for project_name, old_size in db_sizes.items():
            new_size = await get_schema_size(project_name)
            total_reduced_size += old_size - new_size
            logger.info(
                f"Reduced {project_name} database size from "
                f"{format_filesize(old_size)} to {format_filesize(new_size)}"
            )

        logger.info(f"Total reduced size: {format_filesize(total_reduced_size)}")
