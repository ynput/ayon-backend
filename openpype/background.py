import asyncio


class BackgroundTask:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.shutting_down = False
        self.initialize()

    def initialize(self):
        pass

    def start(self):
        self.task = asyncio.create_task(self._run())

    async def shutdown(self):
        if self.task:
            self.task.cancel()

        self.shutting_down = True
        while self.is_running:
            print(f"Waiting for {self.__class__.__name__} to stop")
            await asyncio.sleep(0.1)
        print(f"{self.__class__.__name__} stopped")

    @property
    def is_running(self):
        return self.task and not self.task.done()

    async def _run(self):
        try:
            await self.run()
        except asyncio.CancelledError:
            print(f"{self.__class__.__name__} is cancelled")
            self.shutting_down = True
        except Exception:
            import traceback

            traceback.print_exc()
        finally:
            await self.finalize()
            self.task = None

        if not self.shutting_down:
            print("Restarting", self.__class__.__name__)
            self.start()

    async def run(self):
        pass

    async def finalize(self):
        pass
