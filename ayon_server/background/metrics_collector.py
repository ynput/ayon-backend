import asyncio

from ayon_server.background.background_worker import BackgroundWorker


async def is_connection_available():
    pass


class MetricsCollector(BackgroundWorker):
    """Background task for collecting metrics"""

    async def run(self):
        while True:
            # Not implemented
            await asyncio.sleep(3600)


metrics_collector = MetricsCollector()
