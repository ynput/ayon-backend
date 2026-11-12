import time
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import json_dumps

AYON_INTERNAL_FOLDER_NAME = "__ayon_internal__"

REBUILD_QUERY = f"""

WITH RECURSIVE direct_versions AS (-- folders that directly own a version
    SELECT f.id
    FROM folders f
    WHERE EXISTS (
        SELECT 1
        FROM products p
        JOIN versions v ON v.product_id = p.id
        WHERE p.folder_id = f.id
    )
),

folder_with_versions AS ( -- folders with subfolders that have versions
    SELECT id FROM direct_versions
    UNION
    SELECT f.parent_id
    FROM folder_with_versions fwv
    JOIN folders f ON f.id = fwv.id
    WHERE f.parent_id IS NOT NULL
),

reviewables AS (
    SELECT DISTINCT p.folder_id
    FROM activity_feed af
    JOIN versions v ON v.id = af.entity_id
    JOIN products p ON p.id = v.product_id
    WHERE af.entity_type = 'version'
      AND af.activity_type = 'reviewable'
),

task_agg AS (
    SELECT folder_id,
           count(*)                 AS task_count,
           array_agg(DISTINCT name) AS task_names
    FROM tasks
    GROUP BY folder_id
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
    f.created_by,
    f.updated_by,
    f.data->>'thumbnailHash' AS thumbnail_hash,
    ea.attrib AS all_attrib,
    ea.path   AS path,
    ea.active AS visible,
    f.active  AS active,
    COALESCE(t.task_count, 0)    AS task_count,
    COALESCE(t.task_names, '{{}}') AS task_names,
    (fwv.id IS NOT NULL)         AS has_versions,
    (r.folder_id IS NOT NULL)    AS has_reviewables

FROM folders f
JOIN exported_attributes ea
  ON ea.folder_id = f.id
LEFT JOIN task_agg t
  ON t.folder_id = f.id
LEFT JOIN folder_with_versions fwv
  ON fwv.id = f.id
LEFT JOIN reviewables r
  ON r.folder_id = f.id

WHERE NOT starts_with(ea.path, '{AYON_INTERNAL_FOLDER_NAME}');
"""


async def invalidate_hierarchy_cache(project_name: str) -> None:
    """Drop the cached folder list, also one a running rebuild is about to write."""
    await Redis.incr("project-folders-gen", project_name, ttl=86400)
    await Redis.delete("project-folders", project_name)


async def rebuild_hierarchy_cache(project_name: str) -> list[dict[str, Any]]:
    start_time = time.monotonic()
    generation = await Redis.get("project-folders-gen", project_name)

    result = []
    ids_with_children = set()
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        stmt = await Postgres.prepare(REBUILD_QUERY)
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
                    "task_names": row["task_names"],
                    "status": row["status"],
                    "attrib": row["all_attrib"],
                    "tags": row["tags"],
                    "own_attrib": list(row["attrib"].keys()),
                    "has_reviewables": row["has_reviewables"],
                    "has_versions": row["has_versions"],
                    "thumbnail_hash": row["thumbnail_hash"] or row["id"][-6:],
                    "active": row["active"],
                    "visible": row["visible"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "created_by": row["created_by"],
                    "updated_by": row["updated_by"],
                }
            )
            if row["parent_id"] is not None:
                ids_with_children.add(row["parent_id"])

    for folder in result:
        folder["has_children"] = folder["id"] in ids_with_children

    await Redis.set("project-folders", project_name, json_dumps(result), 3600)
    # invalidated while we were reading: what we just wrote may be stale
    if await Redis.get("project-folders-gen", project_name) != generation:
        await Redis.delete("project-folders", project_name)
    elapsed_time = time.monotonic() - start_time
    logger.trace(
        f"Rebuilt hierarchy cache for {project_name} "
        f"with {len(result)} folders "
        f"in {elapsed_time:.2f}s"
    )
    return result
