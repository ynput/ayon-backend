import time

from ayon_server.cli import app
from ayon_server.helpers.project_list import get_project_list
from ayon_server.helpers.thumbnails.thumbnail_from_reviewable import (
    assign_version_thumbnail_from_reviewable,
)
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


async def process_project_thumbnails(project_name: str) -> None:
    query = f"""
        WITH reviewables AS (
            SELECT DISTINCT ON (a.entity_id)
            a.entity_id AS version_id,
            f.id AS reviewable_id
            FROM project_{project_name}.files f
            JOIN project_{project_name}.activity_feed a
            ON a.activity_id = f.activity_id
            AND a.entity_type = 'version'
            AND a.activity_type = 'reviewable'
            AND a.reference_type = 'origin'
            ORDER BY a.entity_id, a.created_at DESC
        )
        SELECT
            h.path,
            v.id AS version_id,
            v.thumbnail_id,
            r.reviewable_id
        FROM project_{project_name}.versions v

        JOIN project_{project_name}.products p
        ON p.id = v.product_id

        JOIN project_{project_name}.hierarchy h
        ON h.id = p.folder_id

        LEFT JOIN reviewables r
        ON r.version_id = v.id

        WHERE v.thumbnail_id IS NULL
        AND r.reviewable_id IS NOT NULL
        ORDER BY v.created_at DESC
        LIMIT 1000
    """

    rows = await Postgres.fetch(query)
    for row in rows:
        version_id = row["version_id"]
        reviewable_id = row["reviewable_id"]

        await assign_version_thumbnail_from_reviewable(
            project_name,
            reviewable_id,
            version=version_id,
        )


@app.command()
async def generate_version_thumbnails(project_name: str | None = None) -> None:
    """Create thumbnails for versions with reviewables, without thumbnail set"""

    await ayon_init()
    projects = await get_project_list()

    start_time = time.monotonic()
    if project_name is None:
        for project in projects:
            await process_project_thumbnails(project.name)
    else:
        await process_project_thumbnails(project_name)
    elapsed_time = time.monotonic() - start_time

    logger.info(f"Took {elapsed_time:.2f} seconds to process thumbnails")
