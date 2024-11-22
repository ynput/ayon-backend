import asyncio
import datetime

from nxtools import log_traceback, logging


class MaintenanceScheduler:
    hour: int = 3  # run at 3:00 every day
    minute: int = 0
    is_running: bool = False

    async def run(self):
        while True:
            # Calculate the next scheduled time
            now = datetime.datetime.now()
            next_run = datetime.datetime.combine(
                now.date(), datetime.time(self.hour, self.minute)
            )
            if next_run <= now:
                next_run += datetime.timedelta(days=1)

            # Wait until the next run time
            wait_time = (next_run - now).total_seconds()
            logging.debug(f"Scheduled maintenance in {wait_time} seconds.")
            await asyncio.sleep(wait_time)

            # Execute the maintenance task
            await self()

    def start(self):
        if not self.task:
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                print("Maintenance scheduler stopped.")

    async def __call__(self):
        if self.is_running:
            logging.warning("Maintenance task is already running.")
            return
        self.is_running = True
        try:
            print("Starting maintenance...")
            await asyncio.sleep(2)
            print("Maintenance completed.")
        except Exception:
            log_traceback("Maintenance task failed. This should not happen.")
        self.is_running = False
