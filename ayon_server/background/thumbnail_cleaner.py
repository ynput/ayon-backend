import asyncio

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres


async def clear_thumbnails(project_name: str) -> None:
    """Purge unused thumbnails from the database.

    Locate thumbnails not referenced by any folder, version or workfile
    and delete them.

    Delete only thumbnails older than 24 hours.
    """

    # logging.debug(f"Clearing unused thumbnails in {project_name}")

    query = f"""

    DELETE FROM project_{project_name}.thumbnails
        WHERE created_at < 'yesterday'::timestamp
        AND id NOT IN (
            SELECT thumbnail_id FROM project_{project_name}.folders
            UNION
            SELECT thumbnail_id FROM project_{project_name}.versions
            UNION
            SELECT thumbnail_id FROM project_{project_name}.workfiles
        )
    """

    await Postgres.execute(query)


class ThumbnailCleaner(BackgroundWorker):
    """Background task for cleaning unused thumbnails."""

    async def run(self):
        # Execute the first clean-up after a minute, when
        # everything is settled down.

        await asyncio.sleep(60)

        while True:
            projects = await get_project_list()
            for project in projects:
                await clear_thumbnails(project.name)

            # Repeat every hour hours
            await asyncio.sleep(3600)


thumbnail_cleaner = ThumbnailCleaner()
