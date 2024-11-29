from ayon_server.lib.postgres import Postgres
from maintenance.maintenance_task import StudioMaintenanceTask


class VacuumDB(StudioMaintenanceTask):
    description = "Running DB vacuum"

    async def main(self):
        await Postgres.execute("VACUUM FULL")
