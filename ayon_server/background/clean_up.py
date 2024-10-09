import asyncio
import datetime
import time

from nxtools import log_traceback, logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.files import Storages
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres


async def clear_thumbnails(project_name: str) -> None:
    """Purge unused thumbnails from the database.

    Locate thumbnails not referenced by any folder, version or workfile
    and delete them.

    Delete only thumbnails older than 24 hours.
    """

    # keep this outside the query - it's easier to debug this way
    older_cond = "created_at < 'yesterday'::timestamp AND"
    # older_cond = ""

    query = f"""
        DELETE FROM project_{project_name}.thumbnails
        WHERE {older_cond} id NOT IN (
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
        RETURNING id
    """

    storage = await Storages.project(project_name)
    async for row in Postgres.iterate(query):
        await storage.delete_thumbnail(row["id"])


async def clear_activities(project_name: str) -> None:
    """Remove activities that no longer have a corresponding origin

    This can happen when an entity is deleted and there's no activity
    on that entity for a grace period (10 days).

    This does not remove files as their activity_id will be set to NULL
    and they will be deleted by the file clean-up.
    """
    GRACE_PERIOD = 10  # days

    query = f"""
        WITH existing_entities AS (
            SELECT id FROM project_{project_name}.folders
            UNION
            SELECT id FROM project_{project_name}.tasks
            UNION
            SELECT id FROM project_{project_name}.versions
            UNION
            SELECT id FROM project_{project_name}.workfiles
            UNION
            SELECT id FROM project_{project_name}.products
            -- ??? do we need representations ???
        ),

        -- Skip entities that were deleted in the last GRACE_PERIOD days

        recently_deleted_entities AS (
            SELECT (summary->>'entityId')::UUID as entity_id
            FROM events
            WHERE topic LIKE 'entity.%.deleted'
            AND updated_at > now() - interval '{GRACE_PERIOD} days'
            AND project_name = '{project_name}'
            AND summary->>'entityId' IS NOT NULL
        ),

        -- Skip the activities that were updated in the last GRACE_PERIOD days

        grace_period_entity_ids AS (
            SELECT entity_id FROM project_{project_name}.activity_references
            WHERE entity_id IS NOT NULL
            AND updated_at > now() - interval '{GRACE_PERIOD} days'
        ),

        -- Find activities that reference entities that no longer exist

        deletable_activities AS (
            SELECT DISTINCT(activity_id) as activity_id
            FROM project_{project_name}.activity_references
            WHERE entity_id IS NOT NULL
            AND reference_type = 'origin'
            AND entity_id NOT IN (SELECT id FROM existing_entities)
            AND entity_id NOT IN (SELECT entity_id FROM grace_period_entity_ids)
            AND entity_id NOT IN (SELECT entity_id FROM recently_deleted_entities)
        )

        SELECT activity_type, body, data->'origin' as a
        FROM project_{project_name}.activities
        WHERE id IN (SELECT activity_id FROM deletable_activities)
    """

    async for row in Postgres.iterate(query):
        print(project_name, row)


async def clear_actions() -> None:
    """Purge unprocessed launcher actions.

    If an actionr remains in pending state for more than 10 minutes,
    it is considered stale and is deleted. Normally, launcher should
    take action on the event within a few seconds or minutes.
    """
    query = """
        DELETE FROM events
        WHERE
        topic = 'action.launcher'
        AND status = 'pending'
        AND created_at < now() - interval '10 minutes'
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


async def delete_unused_files(project_name: str) -> None:
    storage = await Storages.project(project_name)
    await storage.delete_unused_files()


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
                for prj_func in (
                    clear_thumbnails,
                    clear_activities,
                    delete_unused_files,
                ):
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
