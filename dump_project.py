import asyncio
import time

import typer
from nxtools import logging

from ayon_server.helpers.hierarchy_dump import hierarchy_dump
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres


async def dump_project(
    project_name: str,
    target_path: str,
    root: str | None = None,
    with_activities: bool = False,
):
    await ayon_init()
    start_time = time.monotonic()

    root_id = None
    if root is not None:
        root = root.strip("/")
        q = f"SELECT id FROM project_{project_name}.hierarchy WHERE path = $1"
        res = await Postgres.fetch(q, root)
        if not res:
            raise ValueError(f"Root folder {root} not found")
        root_id = res[0]["id"]
        logging.debug(f"Root folder {root} found: {res[0]['id']}")

    await hierarchy_dump(
        target_zip_path=target_path,
        project_name=project_name,
        root=root_id,
        with_activities=with_activities,
    )
    elapsed_time = time.monotonic() - start_time
    print("**********")
    print(f"Dumped project {project_name}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")
    print("**********")


def main(
    project_name: str,
    dump_path: str,
    root: str | None = None,
    with_activities: bool = False,
):
    asyncio.run(dump_project(project_name, dump_path, root, with_activities))


if __name__ == "__main__":
    typer.run(main)
