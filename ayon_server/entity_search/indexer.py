"""Populate the per-project `entity_search` table (project-wide search, #1285).

Every statement indexes only rows which are missing or whose `updated_at`
differs from the source, so the same code serves the backfill, the repair
sweep and the single-entity update.
"""

__all__ = ["ENTITY_TYPES", "index_entities", "backfill"]

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


def _literal(expr: str, weight: str) -> str:
    """Names are searched literally: one lexeme, not split by the parser."""
    return (
        "setweight(array_to_tsvector(array_remove("
        f"ARRAY[lower(nullif({expr}, ''))], NULL)), '{weight}')"
    )


def _text(expr: str, weight: str) -> str:
    return f"setweight(to_tsvector('simple', coalesce({expr}, '')), '{weight}')"


# Per entity type: the select list
# (id, folder_id, task_id, product_id, version_id, search_vector, updated_at)
# and the FROM clause. The source row is always aliased as `e`.

_UUID_NULL = "NULL::uuid"
_DESCRIPTION = _text("e.attrib->>'description'", "C")

_SOURCES: dict[str, tuple[str, str]] = {
    "folder": (
        f"""
        e.id, e.id, {_UUID_NULL}, {_UUID_NULL}, {_UUID_NULL},
        {_literal("e.name", "A")} || {_text("e.label", "B")} || {_DESCRIPTION},
        e.updated_at
        """,
        "folders e",
    ),
    "task": (
        f"""
        e.id, e.folder_id, e.id, {_UUID_NULL}, {_UUID_NULL},
        {_literal("e.name", "A")} || {_text("e.label", "B")} || {_DESCRIPTION},
        e.updated_at
        """,
        "tasks e",
    ),
    "product": (
        f"""
        e.id, e.folder_id, {_UUID_NULL}, e.id, {_UUID_NULL},
        {_literal("e.name", "A")} || {_DESCRIPTION},
        e.updated_at
        """,
        "products e",
    ),
    # task_id stays empty: the task which produced the version is a different
    # relation and would cascade-delete the row when the task is removed.
    "version": (
        f"""
        e.id, p.folder_id, {_UUID_NULL}, e.product_id, e.id,
        {
            _literal(
                "CASE WHEN e.version < 0 THEN 'HERO' "
                "ELSE 'v' || lpad(e.version::text, 3, '0') END",
                "A",
            )
        }
        || {_DESCRIPTION} || {_text("e.attrib->>'comment'", "C")},
        e.updated_at
        """,
        "versions e JOIN products p ON p.id = e.product_id",
    ),
    # One row per comment; the link columns point to the entity it is on.
    # Comments on deleted or unsupported entities resolve to no folder
    # and are skipped. Link targets are stripped, link texts are kept.
    "comment": (
        f"""
        e.id, COALESCE(t.folder_id, p.folder_id, f.id), t.id, p.id, v.id,
        {_text(r"regexp_replace(e.body, '\]\([^)]*\)', ' ', 'g')", "D")},
        e.updated_at
        """,
        """
        activities e
        JOIN activity_references r
            ON r.activity_id = e.id AND r.reference_type = 'origin'
        LEFT JOIN folders f ON r.entity_type = 'folder' AND f.id = r.entity_id
        LEFT JOIN tasks t ON r.entity_type = 'task' AND t.id = r.entity_id
        LEFT JOIN versions v ON r.entity_type = 'version' AND v.id = r.entity_id
        LEFT JOIN products p ON p.id = COALESCE(
            v.product_id,
            CASE WHEN r.entity_type = 'product' THEN r.entity_id END
        )
        WHERE e.activity_type = 'comment'
        AND COALESCE(t.folder_id, p.folder_id, f.id) IS NOT NULL
        """,
    ),
}

ENTITY_TYPES = list(_SOURCES)


def _build_query(entity_type: str, by_ids: bool) -> str:
    columns, source = _SOURCES[entity_type]
    where = "WHERE" if "WHERE" not in source else "AND"
    ids_cond = "AND e.id = ANY($2::uuid[])" if by_ids else ""
    return f"""
        INSERT INTO entity_search (
            entity_id, folder_id, task_id, product_id, version_id,
            search_vector, updated_at, entity_type
        )
        SELECT {columns}, '{entity_type}'
        FROM {source}
        {where} NOT EXISTS (
            SELECT 1 FROM entity_search s
            WHERE s.entity_id = e.id
            AND s.updated_at IS NOT DISTINCT FROM e.updated_at
        )
        {ids_cond}
        LIMIT $1
        ON CONFLICT (entity_id) DO UPDATE SET
            folder_id = EXCLUDED.folder_id,
            task_id = EXCLUDED.task_id,
            product_id = EXCLUDED.product_id,
            version_id = EXCLUDED.version_id,
            search_vector = EXCLUDED.search_vector,
            updated_at = EXCLUDED.updated_at
    """


async def index_entities(
    project_name: str,
    entity_type: str,
    entity_ids: list[str] | None = None,
    *,
    batch_size: int = 10000,
) -> int:
    """Index missing or outdated rows of one entity type.

    Without `entity_ids`, the whole project is swept. Each batch is committed
    separately, so an interrupted run continues where it stopped.
    Returns the number of indexed rows.
    """
    query = _build_query(entity_type, by_ids=entity_ids is not None)
    args = [batch_size] if entity_ids is None else [batch_size, entity_ids]
    total = 0
    while True:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            status = await Postgres.execute(query, *args, timeout=600)
        count = int(status.split()[-1])  # "INSERT 0 <count>"
        total += count
        if count < batch_size:
            return total
        logger.debug(f"[{project_name}] Indexed {total} {entity_type}s for search")


async def backfill(project_name: str, *, batch_size: int = 10000) -> dict[str, int]:
    """Index everything which is missing or outdated in the project."""
    return {
        entity_type: await index_entities(
            project_name, entity_type, batch_size=batch_size
        )
        for entity_type in ENTITY_TYPES
    }
