import asyncio
import sys
import time

from ayon_server.helpers.hierarchy_dump import hierarchy_dump
from ayon_server.initialize import ayon_init


async def main():
    project_name = sys.argv[-1]
    await ayon_init()
    start_time = time.monotonic()
    await hierarchy_dump(
        "/storage/dump.zip",
        project_name=project_name,
        with_activities=True,
    )
    elapsed_time = time.monotonic() - start_time
    print("**********")
    print(f"Dumped project {project_name}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    print("**********")


if __name__ == "__main__":
    asyncio.run(main())
