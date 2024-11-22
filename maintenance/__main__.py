import asyncio

from ayon_server.initialize import ayon_init
from maintenance.scheduler import MaintenanceScheduler


async def main():
    await ayon_init()
    maintenance = MaintenanceScheduler()
    await maintenance()


if __name__ == "__main__":
    asyncio.run(main())
