from ayon_server.installer import background_installer

from .background_worker import BackgroundWorker
from .log_cleaner import log_cleaner
from .log_collector import log_collector
from .thumbnail_cleaner import thumbnail_cleaner


class BackgroundWorkers:
    def __init__(self):
        self.tasks: list[BackgroundWorker] = [
            background_installer,
            log_collector,
            log_cleaner,
            thumbnail_cleaner,
        ]

    def start(self):
        for task in self.tasks:
            task.start()

    async def shutdown(self):
        for task in self.tasks:
            await task.shutdown()


background_workers = BackgroundWorkers()
