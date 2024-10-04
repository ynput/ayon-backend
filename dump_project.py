import asyncio
import time

from ayon_server.helpers.hierarchy_dump import hierarchy_dump
from ayon_server.initialize import ayon_init


async def main():
    await ayon_init()
    project_name = "demo_commercial"
    start_time = time.monotonic()
    await hierarchy_dump("/storage/dump.zip", project_name=project_name)
    elapsed_time = time.monotonic() - start_time
    print("**********")
    print(f"Dumped project {project_name}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    print("**********")


if __name__ == "__main__":
    asyncio.run(main())
