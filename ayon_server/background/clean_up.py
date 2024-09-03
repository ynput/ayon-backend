import asyncio
import datetime
import time

from nxtools import log_traceback, logging

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


async def clear_logs() -> None:
    """Purge old logs."""

    log_retention = ayonconfig.log_retention_days * 24 * 3600

    now = datetime.datetime.now()
    last_log_to_keep = now - datetime.timedelta(seconds=log_retention)
    delete_from = now - datetime.timedelta(seconds=log_retention * 2)

    # Delete all logs older than the last log to keep

    try:
        res = await Postgres.fetch(
            """
            WITH deleted AS (
                DELETE FROM events WHERE
                topic IN ('log.info', 'log.error', 'log.warning')
                AND created_at > $1
                AND created_at < $2
                RETURNING *
            ) SELECT count(*) as del FROM deleted;
            """,
            delete_from,
            last_log_to_keep,
            timeout=500,
        )

        if res:
            deleted = res[0]["del"]
            if deleted:
                logging.debug(f"Deleted {deleted} old log entries")
    except Exception:
        log_traceback()


async def clear_events() -> None:
    """Purge old events.

    Delete events older than the value specified in ayon-config.
    This is opt-in and by default, old events are not deleted.
    """

    if ayonconfig.event_retention_days is None:
        return

    num_days = ayonconfig.event_retention_days

    while True:
        start_time = time.monotonic()
        res = await Postgres.fetch(
            f"""
            WITH blocked_events AS (
                SELECT DISTINCT(depends_on) as id FROM events
                WHERE depends_on IS NOT NULL
            ),

            deletable_events AS (
                SELECT id
                FROM events
                WHERE updated_at < now() - interval '{num_days} days'
                AND id NOT IN (SELECT id FROM blocked_events)
                ORDER BY updated_at ASC
                LIMIT 5000
            ),

            deleted_events AS(
                DELETE FROM events
                WHERE id IN (SELECT id FROM deletable_events)
                RETURNING id as deleted
            )

            SELECT count(*) as deleted FROM deleted_events;

            """
        )
        deleted = res[0]["deleted"]
        if deleted:
            logging.debug(
                f"Deleted {deleted} old events"
                f" in {time.monotonic() - start_time:.2f} seconds"
            )
        else:
            break


class AyonCleanUp(BackgroundWorker):
    """Background task for periodic clean-up of stuff."""

    async def run(self):
        # Execute the first clean-up after a minue,
        # when everything is settled after the start-up.

        await asyncio.sleep(60)

        while True:
            await self.clear_all()
            await asyncio.sleep(3600)

    async def clear_all(self):
        try:
            projects = await get_project_list()
        except Exception:
            # This should not happen, but if it does, log it and continue
            # We don't want to stop the clean-up process because of this
            log_traceback("Clean-up: Error getting project list")
        else:
            # For each project, clean up thumbnails and unused files
            for project in projects:
                for prj_func in (clear_thumbnails, delete_unused_files):
                    try:
                        await prj_func(project.name)
                    except Exception:
                        log_traceback(
                            f"Error in {prj_func.__name__} for {project.name}"
                        )

        # This clears not project-specific items (events)

        for func in (clear_actions, clear_logs, clear_events):
            try:
                await func()
            except Exception:
                log_traceback(f"Error in {func.__name__}")


clean_up = AyonCleanUp()
