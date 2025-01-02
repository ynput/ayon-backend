import datetime

from ayon_server.lib.postgres import Postgres
from ayon_server.metrics import post_metrics
from maintenance.maintenance_task import StudioMaintenanceTask


async def stats_cleanup():
    now = datetime.datetime.now()
    begin = now - datetime.timedelta(days=60)

    query = "DELETE FROM traffic_stats WHERE date < $1"
    await Postgres().execute(query, begin)


class PushMetrics(StudioMaintenanceTask):
    description = "Pushing metrics"

    async def main(self):
        await post_metrics()
        await stats_cleanup()
