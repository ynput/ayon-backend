import asyncio

from ayon_server.background.background_worker import BackgroundWorker

# from ayon_server.metrics import Metrics


class MetricsCollector(BackgroundWorker):
    """Background task for collecting metrics"""

    async def run(self):
        while True:
            # Not implemented
            await asyncio.sleep(20)
            continue


metrics_collector = MetricsCollector()
