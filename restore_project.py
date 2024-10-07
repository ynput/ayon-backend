import asyncio

import typer
from nxtools import logging

from ayon_server.entities.folder import FolderEntity
from ayon_server.helpers.hierarchy_restore import hierarchy_restore
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres

_ = FolderEntity


async def restore_project(
    project_name: str, dump_path: str, root: str | None = None
) -> None:
    await ayon_init()

    root_id = None
    if root is not None:
        root = root.strip("/")
        q = f"SELECT id FROM project_{project_name}.hierarchy WHERE path = $1"
        res = await Postgres.fetch(q, root)
        if not res:
            raise ValueError(f"Root folder {root} not found")
        root_id = res[0]["id"]
        logging.debug(f"Root folder {root} found: {res[0]['id']}")

    await hierarchy_restore(
        project_name,
        dump_path,
        reindex_entities=True,
        root=root_id,
    )


def main(project_name: str, dump_path: str, root: str | None = None):
    asyncio.run(restore_project(project_name, dump_path, root))


if __name__ == "__main__":
    typer.run(main)
