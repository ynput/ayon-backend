import asyncio

from ayon_server.initialize import ayon_init
from maintenance.scheduler import MaintenanceScheduler


async def main():
    await ayon_init()

    # We run the maintenance tasks from the scheduler
    # to ensure scheduled maintenance is not in progress
    # when executed manually.

    scheduler = MaintenanceScheduler()
    await scheduler.run_maintenance()


if __name__ == "__main__":
    asyncio.run(main())
