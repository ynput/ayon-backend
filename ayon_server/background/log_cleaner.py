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

            # Delete all logs older than the last log to keep

            try:
                res = await Postgres.fetch(
                    """
                    WITH deleted AS (
                        DELETE FROM events WHERE
                        topic LIKE 'log.%' AND
                        created_at < $1
                        RETURNING *
                    ) SELECT count(*) as del FROM deleted;
                    """,
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


log_cleaner = LogCleaner()
