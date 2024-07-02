import asyncio
import datetime

from nxtools import log_traceback, logging

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.config import ayonconfig
from ayon_server.lib.postgres import Postgres


class LogCleaner(BackgroundWorker):
    """Background task for cleaning old logs."""

    async def run(self):
        # Execute the first clean-up after a minute, when
        # everything is settled down.

        log_retention = ayonconfig.log_retention_days * 24 * 3600

        while True:
            # Get the time of the last log to keep

            now = datetime.datetime.now()
            last_log_to_keep = now - datetime.timedelta(seconds=log_retention)
            delete_from = now - datetime.timedelta(seconds=log_retention * 2)

            # Delete all logs older than the last log to keep

            try:
                res = await Postgres.fetch(
                    """
                    WITH deleted AS (
                        DELETE FROM events WHERE
                        topic LIKE 'log.%'
                        AND created_at > $1
                        AND created_at < $2
                        RETURNING *
                    ) SELECT count(*) as del FROM deleted;
                    """,
                    delete_from,
                    last_log_to_keep,
                    timeout=60 * 20,
                )

                if res:
                    deleted = res[0]["del"]
                    if deleted:
                        logging.info(f"Deleted {deleted} old log entries")
            except Exception:
                log_traceback()
                await asyncio.sleep(60)
            else:
                # Repeat every hour hours
                await asyncio.sleep(3600)

        # TODO
        if ayonconfig.event_retention_days is not None:
            num_days = ayonconfig.event_retention_days
            await self.clear_events(num_days=num_days)

    async def clear_events(
        self, condition: str | None = None, num_days: int = 90
    ) -> None:
        # Delete events in batches of 1000
        # to avoid locking the table for too long and potentially
        # causing timeouts in the application

        conditions = [f"updated_at < NOW() - INTERVAL '{num_days} days'"]
        if condition:
            conditions.append(condition)

        while True:
            query = f"""
                WITH deleted AS (
                    DELETE FROM events WHERE id IN (
                        SELECT id FROM events
                        WHERE {' AND '.join(conditions)}
                        ORDER BY updated_at ASC
                        LIMIT 1000
                    )
                SELECT count(*) as del FROM deleted;
            """

            res = await Postgres.fetch(query)

            if res:
                deleted = res[0]["del"]
                if deleted:
                    logging.info(f"Deleted {deleted} old event entries")
                    continue

            await asyncio.sleep(1)
            break


log_cleaner = LogCleaner()
