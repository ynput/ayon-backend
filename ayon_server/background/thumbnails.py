"""
This background process will be used temporarily to scale down thumbnails
and offload the originals to the project storage. In the newer version of
Ayon, this is done automatically during the upload process, but this
is used to process existing thumbnails.
"""

import asyncio

from nxtools import logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_list
from ayon_server.helpers.thumbnails import (
    MAX_THUMBNAIL_HEIGHT,
    MAX_THUMBNAIL_WIDTH,
    ThumbnailProcessNoop,
    process_thumbnail,
)
from ayon_server.lib.postgres import Postgres


async def process_project_thumbnails(project_name: str) -> None:
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
            logging.debug(f"Processing thumbnail {row['id']} in {project_name}")

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


class ThumbnailsProcessing(BackgroundWorker):
    oneshot = True

    async def run(self):
        # await asyncio.sleep(120)
        try:
            projects = await get_project_list()
        except Exception:
            return

        for project in projects:
            await process_project_thumbnails(project.name)
            await asyncio.sleep(0.1)


thumbnails_processing = ThumbnailsProcessing()
