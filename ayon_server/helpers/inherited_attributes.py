import time
from typing import Any

from ayon_server.entities.core import attribute_library
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

_CRAWL_SELECT = """
    SELECT
        h.id,
        h.path,
        f.attrib as own,
        f.active as own_active,
        e.attrib as exported,
        e.path as exported_path,
        e.active as exported_active
    FROM hierarchy h
    INNER JOIN folders f
        ON h.id = f.id
    LEFT JOIN exported_attributes e
        ON h.id = e.folder_id
"""

CRAWL_QUERY = _CRAWL_SELECT + "ORDER BY h.path ASC"

# The subtree is walked using parent_id, not selected by a path prefix:
# LIKE would treat the underscores in folder names as wildcards.
SUBTREE_CRAWL_QUERY = f"""
    WITH RECURSIVE subtree AS (
        SELECT id FROM folders WHERE id = ANY($1::uuid[])
        UNION
        SELECT c.id FROM folders c INNER JOIN subtree s ON c.parent_id = s.id
    )
    {_CRAWL_SELECT}
    WHERE h.id IN (SELECT id FROM subtree)
    ORDER BY h.path ASC
"""

# Exported attributes of the parents of the given folders
PARENTS_QUERY = """
    SELECT f.parent_id, h.path, e.attrib, e.active
    FROM folders f
    INNER JOIN hierarchy h
        ON h.id = f.parent_id
    LEFT JOIN exported_attributes e
        ON e.folder_id = f.parent_id
    WHERE f.id = ANY($1::uuid[])
"""

UPSERT_QUERY = """
    INSERT INTO exported_attributes (folder_id, path, attrib, active)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (folder_id)
    DO UPDATE SET
        path = EXCLUDED.path,
        attrib = EXCLUDED.attrib,
        active = EXCLUDED.active
"""


async def refresh_hierarchy_view(project_name: str) -> None:
    """Refresh the hierarchy materialized view (folder paths) of the project."""
    view = f"project_{project_name}.hierarchy"
    async with Postgres.transaction():
        # REFRESH takes its snapshot before it waits for the lock on the view,
        # so it would miss the folders committed while it waited (and drop
        # them from the view). Take the lock first, using a refresh that reads
        # nothing: LOCK TABLE does not work on materialized views.
        await Postgres.execute(f"REFRESH MATERIALIZED VIEW {view} WITH NO DATA")
        await Postgres.execute(f"REFRESH MATERIALIZED VIEW {view}")


async def _rebuild_from(
    project_attrib: dict[str, Any],
    folder_ids: list[str] | None = None,
) -> None:
    """Rebuild the exported attributes of the project folders.

    When folder_ids is set, only these folders and their descendants are
    rebuilt. The hierarchy view must be up to date.
    """
    inheritable = attribute_library.inheritable

    # path: attrib_set cache to use when returning from child to parent
    caching: dict[tuple[str, ...], dict[str, Any]] = {}
    active_caching: dict[tuple[str, ...], bool] = {}

    args: tuple[Any, ...] = ()
    if folder_ids is not None:
        # Start from what the parents export. A parent that is rebuilt as well
        # comes first in the crawl and replaces its record here.
        rebuilt = set(folder_ids)
        for row in await Postgres.fetch(PARENTS_QUERY, folder_ids):
            if row["attrib"] is None:
                if row["parent_id"] in rebuilt:
                    continue
                logger.warning(
                    f"Folder {row['path']} has no exported attributes. "
                    "Rebuilding the whole project."
                )
                return await _rebuild_from(project_attrib)
            parent_path = tuple(row["path"].split("/"))
            caching[parent_path] = {
                k: v for k, v in row["attrib"].items() if k in inheritable
            }
            active_caching[parent_path] = row["active"]
        st_crawl = await Postgres.prepare(SUBTREE_CRAWL_QUERY)
        args = (folder_ids,)
    else:
        st_crawl = await Postgres.prepare(CRAWL_QUERY)

    st_upsert = await Postgres.prepare(UPSERT_QUERY)

    current_attrib_set: dict[str, Any] = {}
    current_active = True
    buff: list[tuple[str, str, dict[str, Any], bool]] = []

    async for record in st_crawl.cursor(*args, prefetch=1000):
        path_elements = tuple(record["path"].split("/"))
        if len(path_elements) == 1:
            current_attrib_set = project_attrib.copy()
            current_active = True

        elif path_elements[:-1] in caching:
            current_attrib_set = caching[path_elements[:-1]]
            current_active = active_caching[path_elements[:-1]]

        # Exported attributes are the inherited and own values combined,
        # but only the inheritable ones are passed to the children
        new_attrib_set = current_attrib_set.copy()
        new_attrib_set.update(record["own"])
        children_attrib_set = {
            k: v for k, v in new_attrib_set.items() if k in inheritable
        }

        new_active = current_active and record["own_active"]

        caching[path_elements] = children_attrib_set
        active_caching[path_elements] = new_active

        if (
            record["exported"] != new_attrib_set
            or record["exported_path"] != record["path"]
            or record["exported_active"] != new_active
        ):
            buff.append(
                (
                    record["id"],
                    record["path"],
                    new_attrib_set,
                    new_active,
                )
            )

        if len(buff) > 100:
            await st_upsert.executemany(buff)
            buff = []

        current_attrib_set = children_attrib_set
        current_active = new_active

    if buff:
        await st_upsert.executemany(buff)


async def rebuild_inherited_attributes(
    project_name: str,
    pattr: dict[str, Any] | None = None,
    *,
    refresh_hierarchy: bool = True,
    folder_ids: list[str] | None = None,
    **kwargs,  # TODO: catch kwargs and log deprecation warning
):
    """Rebuild inherited attributes for all objects in the project.

    When folder_ids is set, only these folders and their descendants are
    rebuilt (an empty list only refreshes the hierarchy, if requested).
    Use it when nothing else changed: a changed project attribute or
    attribute definition needs a rebuild of the whole project.

    Rebuilds of a project run one at a time: a partial rebuild starts from
    what the parents export, which another rebuild may be about to change.
    Don't call this in a transaction that already read the hierarchy view
    or changed the exported attributes (the lock order may deadlock).
    """
    if not refresh_hierarchy and folder_ids is not None and not folder_ids:
        return

    start = time.perf_counter()

    async with Postgres.transaction():
        await Postgres.advisory_xact_lock(
            f"inherited-attributes:{project_name.lower()}"
        )
        await Postgres.set_project_schema(project_name)

        if refresh_hierarchy:
            logger.trace(f"Refreshing {project_name} hierarchy")
            await refresh_hierarchy_view(project_name)

        if folder_ids is not None and not folder_ids:
            return

        if pattr is None:
            project_attrib = attribute_library.project_defaults
            res = await Postgres.fetch(
                "SELECT attrib FROM public.projects WHERE name = $1", project_name
            )
            project_attrib.update(res[0]["attrib"])
        else:
            project_attrib = pattr.copy()

        # Only inheritable attributes are inherited
        project_attrib = {
            name: value
            for name, value in project_attrib.items()
            if name in attribute_library.inheritable
        }

        await _rebuild_from(project_attrib, folder_ids)

    elapsed = time.perf_counter() - start
    scope = "all" if folder_ids is None else len(folder_ids)
    logger.trace(
        f"Rebuilt inherited attributes for {project_name} "
        f"({scope} folders) in {elapsed:.2f}s"
    )
