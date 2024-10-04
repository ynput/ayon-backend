import asyncio

from ayon_server.helpers.dump_hierarchy import dump_hierarchy
from ayon_server.initialize import ayon_init


async def main():
    await ayon_init()
    await dump_hierarchy("/storage/dump.zip", "demo_commercial")


if __name__ == "__main__":
    asyncio.run(main())
