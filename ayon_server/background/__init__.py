from ayon_server.installer import background_installer

from .background_worker import BackgroundWorker
from .log_collector import log_collector
from .thumbnail_cleaner import thumbnail_cleaner


class BackgroundWorkers:
    def __init__(self):
        self.tasks: list[BackgroundWorker] = [
            background_installer,
            log_collector,
            thumbnail_cleaner,
        ]

    async def start(self):
        for task in self.tasks:
            await task.start()

    async def shutdown(self):
        for task in self.tasks:
            await task.shutdown()


background_workers = BackgroundWorkers()
