from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from maintenance.maintenance_task import StudioMaintenanceTask


class RemoveInactiveWorkers(StudioMaintenanceTask):
    description = "Removing inactive workers"

    async def main(self):
        query = """
            SELECT h.name
            FROM hosts h
            WHERE h.last_seen < NOW() - INTERVAL '1 day'
            AND NOT EXISTS (
                SELECT 1
                FROM services s
                WHERE s.hostname = h.name
            );
        """

        candidates = await Postgres.fetch(query)
        if not candidates:
            return

        for row in candidates:
            hostname = row["name"]
            await Postgres.execute("DELETE FROM hosts WHERE name = $1", hostname)
            logger.info(f"Removed inactive worker: {hostname}")
