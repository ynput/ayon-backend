import asyncio
import sys

from ayon_server.initialize import ayon_init
from maintenance.scheduler import MaintenanceScheduler


async def main():
    await ayon_init()

    # We run the maintenance tasks from the scheduler
    # to ensure scheduled maintenance is not in progress
    # when executed manually.

    scheduler = MaintenanceScheduler()

    if "--task" in sys.argv:
        task_index = sys.argv.index("--task") + 1
        if task_index < len(sys.argv):
            task_name = sys.argv[task_index]
            await scheduler.run_maintenance(task_name=task_name)
        else:
            print("Error: --task argument requires a task name.")
    elif "--one-shot" in sys.argv:
        await scheduler.run_maintenance()
    else:
        await scheduler.run()


if __name__ == "__main__":
    asyncio.run(main())
