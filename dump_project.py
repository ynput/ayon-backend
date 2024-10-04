import asyncio

from ayon_server.helpers.hierarchy_dump import hierarchy_dump
from ayon_server.initialize import ayon_init


async def main():
    await ayon_init()
    await hierarchy_dump("/storage/dump.zip", "demo_commercial")


if __name__ == "__main__":
    asyncio.run(main())
