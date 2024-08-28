import asyncio
import time

from nxtools import logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
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


async def clear_events() -> None:
    """Purge old events.

    Delete events older than the value specified in ayon-config.
    This is opt-in and by default, old events are not deleted.
    """

    if ayonconfig.event_retention_days is None:
        return

    num_days = ayonconfig.event_retention_days

    query = f"""
        WITH dependent_events AS (
            SELECT DISTINCT event_id FROM events
            WHERE updated_at >= now() - interval '{num_days} days'
            AND depends_on IS NOT NULL
        )

        WITH deleted AS (
            DELETE FROM events WHERE
            updated_at < now() - interval '{num_days} days'
            AND id NOT IN (SELECT event_id FROM dependent_events)
        )

        SELECT count(*) as del FROM deleted;
    """

    start_time = time.monotonic()
    res = await Postgres.fetch(query)
    elapsed = time.monotonic() - start_time
    if res:
        deleted = res[0]["del"]
        if deleted:
            logging.debug(f"Deleted {deleted} old events")
        if elapsed > 1:
            logging.debug(f"Event clean-up took {elapsed:.2f} seconds")


class AyonCleanUp(BackgroundWorker):
    """Background task for periodic clean-up of stuff."""

    async def run(self):
        # Execute the first clean-up after a minute, when
        # everything is settled down.

        await asyncio.sleep(120)

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
        await clear_events()


clean_up = AyonCleanUp()
