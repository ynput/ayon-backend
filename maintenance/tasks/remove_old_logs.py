import datetime

from ayon_server.config import ayonconfig
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback, logger
from maintenance.maintenance_task import StudioMaintenanceTask


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
                DELETE FROM public.events WHERE
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
                logger.debug(f"Deleted {deleted} old log entries")
    except Exception:
        log_traceback()


class RemoveOldLogs(StudioMaintenanceTask):
    description = "Removing old logs"

    async def main(self):
        await clear_logs()
