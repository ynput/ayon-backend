import time
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import json_dumps


async def rebuild_hierarchy_cache(project_name: str) -> list[dict[str, Any]]:
    start_time = time.monotonic()
    query = f"""
        WITH reviewables AS (
            SELECT p.folder_id AS folder_id
            FROM project_{project_name}.activity_feed af
            INNER JOIN project_{project_name}.versions v
            ON af.entity_id = v.id
            AND af.entity_type = 'version'
            AND  af.activity_type = 'reviewable'
            INNER JOIN project_{project_name}.products p
            ON p.id = v.product_id
        )

        SELECT
            f.id,
            f.parent_id,
            f.name,
            f.label,
            f.folder_type,
            f.status,
            f.attrib,
            f.tags,
            f.updated_at,
            ea.attrib as all_attrib,
            ea.path as path,
            COUNT (tasks.id) AS task_count,
            array_agg(tasks.name) AS task_names,
            EXISTS (SELECT 1 FROM reviewables WHERE folder_id = f.id) AS has_reviewables
        FROM
            project_{project_name}.folders f
        INNER JOIN
            project_{project_name}.exported_attributes ea
        ON f.id = ea.folder_id
        LEFT JOIN
            project_{project_name}.tasks AS tasks
        ON
            tasks.folder_id = f.id
        GROUP BY f.id, ea.attrib, ea.path
    """

    result = []
    ids_with_children = set()
    async for row in Postgres.iterate(query):
        result.append(
            {
                "id": row["id"],
                "path": row["path"],
                "parent_id": row["parent_id"],
                "parents": row["path"].strip("/").split("/")[:-1],
                "name": row["name"],
                "label": row["label"],
                "folder_type": row["folder_type"],
                "has_tasks": row["task_count"] > 0,
                "task_names": row["task_names"] if row["task_names"] != [None] else [],
                "status": row["status"],
                "attrib": row["all_attrib"],
                "tags": row["tags"],
                "own_attrib": list(row["attrib"].keys()),
                "has_reviewables": row["has_reviewables"],
                "updated_at": row["updated_at"],
            }
        )
        if row["parent_id"] is not None:
            ids_with_children.add(row["parent_id"])

    for folder in result:
        folder["has_children"] = folder["id"] in ids_with_children

    await Redis.set("project.folders", project_name, json_dumps(result), 3600)
    elapsed_time = time.monotonic() - start_time
    logger.trace(
        f"Rebuilt hierarchy cache for {project_name} "
        f"with {len(result)} folders "
        f"in {elapsed_time:.2f}s"
    )
    return result
