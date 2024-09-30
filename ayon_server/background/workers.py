from ayon_server.installer import background_installer

from .background_worker import BackgroundWorker
from .clean_up import clean_up
from .log_collector import log_collector
from .metrics_collector import metrics_collector
from .thumbnails import thumbnails_processing


class BackgroundWorkers:
    def __init__(self):
        self.tasks: list[BackgroundWorker] = [
            background_installer,
            log_collector,
            metrics_collector,
            clean_up,
            thumbnails_processing,
        ]

    def start(self):
        for task in self.tasks:
            task.start()

    async def shutdown(self):
        for task in self.tasks:
            await task.shutdown()


background_workers = BackgroundWorkers()
