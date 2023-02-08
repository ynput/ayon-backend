import asyncio

from ayon_server.background import BackgroundTask
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


class ThumbnailCleaner(BackgroundTask):
    """Background task for cleaning unused thumbnails."""

    async def run(self):
        # Execute the first clean-up after a minute, when
        # everything is settled down.

        await asyncio.sleep(60)

        while True:
            projects = [
                row["name"]
                async for row in Postgres.iterate("SELECT name FROM projects")
            ]

            for project in projects:
                await clear_thumbnails(project)

            # Repeat every hour hours
            await asyncio.sleep(3600)


thumbnail_cleaner = ThumbnailCleaner()
