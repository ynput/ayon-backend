from ayon_server.metrics import post_metrics
from maintenance.maintenance_task import StudioMaintenanceTask


class PushMetrics(StudioMaintenanceTask):
    description = "Pushing metrics"

    async def main(self):
        await post_metrics()
