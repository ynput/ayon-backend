from ayon_server.installer import background_installer

from .background_worker import BackgroundWorker
from .invalidate_actions import invalidate_actions
from .log_collector import log_collector


class BackgroundWorkers:
    """
    This class holds all background workers that we require to run.
    (well. not all - messaging is handled separately in ayon_server.api.server,
    but you get the idea).

    Server calls "start" when the server is initialized, so all workers become
    available in whenever server is running.

    That effectively means that separate processes (cli tools, crotab jobs, setup,
    and maintenance script) cannot rely on the workers. Cli tools for example
    don't store logs in the database.
    """

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
