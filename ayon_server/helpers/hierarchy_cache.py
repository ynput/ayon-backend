import time
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import json_dumps


async def rebuild_hierarchy_cache(project_name: str) -> list[dict[str, Any]]:
    start_time = time.monotonic()
    query = f"""
        WITH RECURSIVE reviewables AS (
            SELECT p.folder_id AS folder_id
            FROM project_{project_name}.activity_feed af
            INNER JOIN project_{project_name}.versions v
            ON af.entity_id = v.id
            AND af.entity_type = 'version'
            AND  af.activity_type = 'reviewable'
            INNER JOIN project_{project_name}.products p
            ON p.id = v.product_id
        ),

        folder_closure AS (
            SELECT id AS ancestor_id, id AS descendant_id
            FROM project_{project_name}.folders
            UNION ALL
            SELECT fc.ancestor_id, f.id AS descendant_id
            FROM folder_closure fc
            JOIN project_{project_name}.folders f
            ON f.parent_id = fc.descendant_id
        ),

        folder_with_versions AS (
            SELECT DISTINCT fc.ancestor_id
            FROM folder_closure fc
            JOIN project_{project_name}.products p ON p.folder_id = fc.descendant_id
            JOIN project_{project_name}.versions v ON v.product_id = p.id
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
            f.created_at,
            f.updated_at,
            ea.attrib as all_attrib,
            ea.path as path,
            COUNT (tasks.id) AS task_count,
            array_agg(DISTINCT tasks.name) AS task_names,
            (fwv.ancestor_id IS NOT NULL)::BOOLEAN AS has_versions,
            (r.folder_id IS NOT NULL)::BOOLEAN AS has_reviewables

        FROM project_{project_name}.folders f

        INNER JOIN project_{project_name}.exported_attributes ea
        ON f.id = ea.folder_id

        LEFT JOIN project_{project_name}.tasks AS tasks
        ON tasks.folder_id = f.id

        LEFT JOIN folder_with_versions fwv
        ON fwv.ancestor_id = f.id

        LEFT JOIN reviewables r
        ON r.folder_id = f.id

        GROUP BY f.id, ea.attrib, ea.path, fwv.ancestor_id, r.folder_id
    """

    result = []
    ids_with_children = set()
    async with Postgres.transaction():
        # Since this is ALWAYS called after rebuild_inherited_attributes,
        # we don't need to refresh materialized views here.
        stmt = await Postgres.prepare(query)
        async for row in stmt.cursor():
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
                    "task_names": row["task_names"]
                    if row["task_names"] != [None]
                    else [],
                    "status": row["status"],
                    "attrib": row["all_attrib"],
                    "tags": row["tags"],
                    "own_attrib": list(row["attrib"].keys()),
                    "has_reviewables": row["has_reviewables"],
                    "has_versions": row["has_versions"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
            if row["parent_id"] is not None:
                ids_with_children.add(row["parent_id"])

    for folder in result:
        folder["has_children"] = folder["id"] in ids_with_children

    await Redis.set("project-folders", project_name, json_dumps(result), 3600)
    elapsed_time = time.monotonic() - start_time
    logger.trace(
        f"Rebuilt hierarchy cache for {project_name} "
        f"with {len(result)} folders "
        f"in {elapsed_time:.2f}s"
    )
    return result
