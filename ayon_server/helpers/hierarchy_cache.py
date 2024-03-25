import time
from typing import Any

import asyncpg
from nxtools import logging

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import json_dumps


async def rebuild_hierarchy_cache(
    project_name: str,
    transaction: asyncpg.Connection | None = None,
) -> list[dict[str, Any]]:
    start_time = time.monotonic()
    query = f"""
        SELECT
            f.id, f.parent_id, f.name, f.folder_type, f.status, f.attrib,
            ea.attrib as all_attrib, ea.path as path
        FROM
            project_{project_name}.folders f
        INNER JOIN
            project_{project_name}.exported_attributes ea
        ON f.id = ea.folder_id
    """

    result = []
    async for row in Postgres.iterate(query, transaction=transaction):
        # save microseconds by not converting to entity type
        result.append(
            {
                "id": row["id"],
                "path": row["path"],
                "parent_id": row["parent_id"],
                "name": row["name"],
                "folder_type": row["folder_type"],
                "status": row["status"],
                "attrib": row["all_attrib"],
                "own_attrib": list(row["attrib"].keys()),
            }
        )
    await Redis.set("project.folders", project_name, json_dumps(result), 3600)
    elapsed_time = time.monotonic() - start_time
    logging.debug(f"Rebuilt hierarchy cache for {project_name} in {elapsed_time:.2f} s")
    return result
