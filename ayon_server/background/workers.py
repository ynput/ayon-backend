from ayon_server.installer import background_installer

from .auto_update import auto_update
from .background_worker import BackgroundWorker
from .clean_up import clean_up
from .log_collector import log_collector
from .metrics_collector import metrics_collector


class BackgroundWorkers:
    def __init__(self):
        self.tasks: list[BackgroundWorker] = [
            auto_update,
            background_installer,
            log_collector,
            metrics_collector,
            clean_up,
        ]

    def start(self):
        for task in self.tasks:
            task.start()

    async def shutdown(self):
        for task in self.tasks:
            await task.shutdown()


background_workers = BackgroundWorkers()
