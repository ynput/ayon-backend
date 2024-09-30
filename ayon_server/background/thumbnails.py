"""
This background process will be used temporarily to scale down thumbnails
and offload the originals to the project storage. In the newer version of
Ayon, this is done automatically during the upload process, but this
is used to process existing thumbnails.
"""

import asyncio

from nxtools import logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres


async def process_project_thumbnails(project_name: str) -> None:
    q = f"""
        SELECT count(*) FROM project_{project_name}.thumbnails
        WHERE meta = '{{}}'
        """

    res = await Postgres.fetch(q)
    count = res[0]["count"]
    if count == 0:
        return

    logging.debug(f"{count} unprocessed thumbnails in {project_name}")


class ThumbnailsProcessing(BackgroundWorker):
    async def run(self):
        # await asyncio.sleep(120)
        try:
            projects = await get_project_list()
        except Exception:
            return

        for project in projects:
            await process_project_thumbnails(project.name)
            await asyncio.sleep(0.1)

        await self.shutdown()


thumbnails_processing = ThumbnailsProcessing()
