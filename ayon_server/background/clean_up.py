import asyncio

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.helpers.project_files import delete_unused_files
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres


async def clear_thumbnails(project_name: str) -> None:
    """Purge unused thumbnails from the database.

    Locate thumbnails not referenced by any folder, version or workfile
    and delete them.

    Delete only thumbnails older than 24 hours.
    """

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


async def clear_actions() -> None:
    """Purge unprocessed launcher actions.

    If an actionr remains in pending state for more than 30 minutes,
    it is considered stale and is deleted. Normally, launcher should
    take action on the event within a few seconds or minutes.
    """
    query = """
        DELETE FROM events
        WHERE
        topic = 'action.launcher'
        AND status = 'pending'
        AND created_at < now() - interval '30 minutes'
    """
    await Postgres.execute(query)


class AyonCleanUp(BackgroundWorker):
    """Background task for periodic clean-up of stuff."""

    async def run(self):
        # Execute the first clean-up after a minute, when
        # everything is settled down.

        await asyncio.sleep(60)

        while True:
            try:
                await self.clean_all()
            except Exception as e:
                print(f"Error in clean-up: {e}")
            await asyncio.sleep(3600)

    async def clean_all(self):
        projects = await get_project_list()
        for project in projects:
            await clear_thumbnails(project.name)
            await delete_unused_files(project.name)

        await clear_actions()


clean_up = AyonCleanUp()
