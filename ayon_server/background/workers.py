from ayon_server.installer import background_installer

from .background_worker import BackgroundWorker
from .invalidate_actions import invalidate_actions
from .log_collector import log_collector


class BackgroundWorkers:
    def __init__(self):
        self.tasks: list[BackgroundWorker] = [
            background_installer,
            invalidate_actions,
            log_collector,
        ]

    def start(self):
        for task in self.tasks:
            task.start()

    async def shutdown(self):
        for task in self.tasks:
            await task.shutdown()


background_workers = BackgroundWorkers()
