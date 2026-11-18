"""Populate the per-project `entity_search` table.

Every entity type has a source: a SELECT returning its search rows
(entity_id, folder_id, task_id, product_id, version_id, literals,
search_vector, updated_at). A row is indexed when it is missing or its
`updated_at` differs from the source, so the same code serves the backfill,
the repair sweep and single updates.

A row also depends on its parents: the folder path is part of its
literals and the links follow moved parents. When a row's folder,
product or literals change, the rows below it are marked outdated
(`updated_at = NULL`) and indexed again.
"""

__all__ = ["ENTITY_TYPES", "backfill", "index_entities"]

from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

ENTITY_TYPES = ["folder", "task", "product", "version", "comment"]  # parents first

#
# Expressions building the documents
#


def text_vector(expr: str, whole_weight: str, part_weight: str) -> str:
    """Return a tsvector of the words of a text, matching from word starts.

    Tokens are indexed whole with `whole_weight` ("camel_case", "render.exr")
    and split on punctuation with `part_weight` ("camel", "case", "render",
    "exr"). Underscores become hyphens: the parser keeps hyphenated words
    whole and also splits them. Accents are removed (on the query side too).
    """
    text = f"public.unaccent(coalesce({expr}, ''))"
    whole = f"to_tsvector('simple', translate({text}, '_', '-'))"
    parts = f"to_tsvector('simple', regexp_replace({text}, '[^[:alnum:]]+', ' ', 'g'))"
    return (
        f"setweight({whole}, '{whole_weight}') || setweight({parts}, '{part_weight}')"
    )


def literal_text(*exprs: str) -> str:
    """Return the path, names and labels: not split, matched anywhere."""
    return f"lower(public.unaccent(concat_ws(' ', {', '.join(exprs)})))"


def attribute_vector(entity_type: str) -> str:
    """Return a tsvector of the description and free-text attributes of `e`.

    Free-text attributes are strings without an enum. Their names are part
    of the query: they come from the attribute definitions, which rarely change.
    """
    # Imported here: the entities import the indexer to enqueue their saves
    from ayon_server.entities.core.attrib import attribute_library

    attributes = [
        f"e.attrib->>'{attr['name']}'"
        for attr in attribute_library[entity_type]
        if attr.get("type") == "string"
        and attr["name"] != "description"  # has its own, higher weight
        and attr["name"].isalnum()  # always true, but it is inlined into SQL
        and not attr.get("enum")
        and not attr.get("enumResolver")
    ]
    description = text_vector("e.attrib->>'description'", "B", "C")
    attributes_text = f"concat_ws(' ', {', '.join(attributes) or 'NULL'})"
    return f"{description} || {text_vector(attributes_text, 'C', 'D')}"


#
# Sources
#

# Folder paths (the `paths` CTE used by the sources), from the folders table:
# the hierarchy view may not be refreshed yet when the indexer runs.
FOLDER_PATHS_CTE = """
    WITH RECURSIVE paths AS (
        SELECT id, name::text AS path FROM folders WHERE parent_id IS NULL
        UNION ALL
        SELECT f.id, pa.path || '/' || f.name
        FROM folders f JOIN paths pa ON f.parent_id = pa.id
    )
"""


def get_folder_source() -> str:
    return f"""
        SELECT e.id, e.id, NULL::uuid, NULL::uuid, NULL::uuid,
            {literal_text("pa.path", "e.label")},
            {attribute_vector("folder")},
            e.updated_at
        FROM folders e
        JOIN paths pa ON pa.id = e.id
    """


def get_task_source() -> str:
    return f"""
        SELECT e.id, e.folder_id, e.id, NULL::uuid, NULL::uuid,
            {literal_text("pa.path", "e.name", "e.label", "e.task_type")},
            {attribute_vector("task")},
            e.updated_at
        FROM tasks e
        JOIN paths pa ON pa.id = e.folder_id
    """


def get_product_source() -> str:
    return f"""
        SELECT e.id, e.folder_id, NULL::uuid, e.id, NULL::uuid,
            {literal_text("pa.path", "e.name")},
            {attribute_vector("product")},
            e.updated_at
        FROM products e
        JOIN paths pa ON pa.id = e.folder_id
    """


def get_version_source() -> str:
    # task_id stays empty: the task which produced the version is a different
    # relation and would cascade-delete the row when the task is removed.
    version_name = (
        "CASE WHEN e.version < 0 THEN 'HERO'"
        " ELSE 'v' || lpad(e.version::text, 3, '0') END"
    )
    return f"""
        SELECT e.id, p.folder_id, NULL::uuid, e.product_id, e.id,
            {literal_text("pa.path", "p.name", version_name)},
            {attribute_vector("version")},
            e.updated_at
        FROM versions e
        JOIN products p ON p.id = e.product_id
        JOIN paths pa ON pa.id = p.folder_id
    """


def get_comment_source() -> str:
    """One row per comment, linked to the entity it is on.

    Comments on deleted or unsupported entities resolve to no folder and are
    skipped. No literals: they would rank every comment of a folder above its
    tasks. Markdown link targets are stripped, link texts are kept.
    """
    body = r"regexp_replace(e.body, '\]\([^)]*\)', ' ', 'g')"
    return f"""
        SELECT e.id, COALESCE(t.folder_id, p.folder_id, f.id), t.id, p.id, v.id,
            NULL,
            {text_vector(body, "B", "C")},
            e.updated_at
        FROM activities e
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
    """


def get_source(entity_type: str) -> str:
    match entity_type:
        case "folder":
            return get_folder_source()
        case "task":
            return get_task_source()
        case "product":
            return get_product_source()
        case "version":
            return get_version_source()
        case "comment":
            return get_comment_source()
    raise ValueError(f"Unsupported entity type for search: {entity_type}")


def build_upsert_query(entity_type: str) -> str:
    """Return the query indexing a batch of outdated rows.

    $1 = batch size, $2 = entity ids or NULL for all.
    """
    paths_cte = "" if entity_type == "comment" else FOLDER_PATHS_CTE

    query = f"""
        {paths_cte}
        INSERT INTO entity_search (
            entity_id, folder_id, task_id, product_id, version_id,
            literals, search_vector, updated_at, entity_type
        )
        SELECT src.*, '{entity_type}' FROM ({get_source(entity_type)}) AS src (
            entity_id, folder_id, task_id, product_id, version_id,
            literals, search_vector, updated_at
        )
        WHERE NOT EXISTS (
            SELECT 1 FROM entity_search s
            WHERE s.entity_id = src.entity_id
            AND s.updated_at IS NOT DISTINCT FROM src.updated_at
        )
        AND ($2::uuid[] IS NULL OR src.entity_id = ANY($2))
        LIMIT $1
        ON CONFLICT (entity_id) DO UPDATE SET
            folder_id = EXCLUDED.folder_id,
            task_id = EXCLUDED.task_id,
            product_id = EXCLUDED.product_id,
            version_id = EXCLUDED.version_id,
            literals = EXCLUDED.literals,
            search_vector = EXCLUDED.search_vector,
            updated_at = EXCLUDED.updated_at
    """
    return query


#
# Dependent rows
#

# What the rows below an entity take from its row
SELECT_INHERITED_VALUES = """
    SELECT entity_id, folder_id, product_id, literals FROM entity_search
    WHERE entity_id = ANY($1::uuid[])
"""


def build_mark_dependents_outdated_query(entity_type: str) -> str:
    """Return the query marking the rows below the entities ($1) outdated.

    A folder's subtree has a new path (comments have none, their links stay),
    a product's versions and comments a new folder, the comments of a task
    or version a new folder or product. Returns the marked rows.
    """
    return f"""
        WITH RECURSIVE subtree AS (
            SELECT id FROM folders WHERE '{entity_type}' = 'folder' AND id = ANY($1)
            UNION
            SELECT f.id FROM folders f JOIN subtree st ON f.parent_id = st.id
        )
        UPDATE entity_search SET updated_at = NULL
        WHERE entity_id <> ALL($1) AND (
            (folder_id IN (SELECT id FROM subtree) AND entity_type <> 'comment')
            OR {entity_type}_id = ANY($1)
        )
        RETURNING entity_type, entity_id
    """


#
# Indexing
#


async def fetch_from_project(project_name: str, query: str, *args: Any) -> list[Any]:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        return await Postgres.fetch(query, *args, timeout=600)


async def index_outdated_rows(
    project_name: str,
    entity_type: str,
    entity_ids: list[str] | None,
    batch_size: int,
) -> int:
    """Index outdated rows in batches, each committed on its own."""
    query = build_upsert_query(entity_type)
    total = 0
    while True:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            status = await Postgres.execute(query, batch_size, entity_ids, timeout=600)
        count = int(status.split()[-1])  # "INSERT 0 <count>"
        total += count
        if count < batch_size:
            return total
        logger.debug(f"[{project_name}] Indexed {total} {entity_type}s for search")


async def reindex_dependents(
    project_name: str,
    entity_type: str,
    changed_ids: list[str],
    batch_size: int,
) -> None:
    """Index the rows below moved or renamed entities again."""
    query = build_mark_dependents_outdated_query(entity_type)
    outdated: dict[str, list[str]] = {}
    for row in await fetch_from_project(project_name, query, changed_ids):
        outdated.setdefault(row["entity_type"], []).append(row["entity_id"])
    for dependent_type in ENTITY_TYPES:
        if ids := outdated.get(dependent_type):
            await index_outdated_rows(project_name, dependent_type, ids, batch_size)


async def index_entities(
    project_name: str,
    entity_type: str,
    entity_ids: list[str] | None = None,
    *,
    batch_size: int = 10000,
) -> int:
    """Index missing or outdated rows of one entity type.

    Without `entity_ids`, the whole project is swept (moved parents are not
    detected then). With them, the rows below entities which moved or were
    renamed are indexed again. Returns the number of indexed rows of the type.
    """
    if entity_ids is None or entity_type == "comment":
        return await index_outdated_rows(
            project_name, entity_type, entity_ids, batch_size
        )

    before = await fetch_from_project(project_name, SELECT_INHERITED_VALUES, entity_ids)
    total = await index_outdated_rows(project_name, entity_type, entity_ids, batch_size)
    after = await fetch_from_project(project_name, SELECT_INHERITED_VALUES, entity_ids)

    after_by_id = {row["entity_id"]: row for row in after}
    changed_ids = [
        row["entity_id"] for row in before if after_by_id.get(row["entity_id"]) != row
    ]
    if changed_ids:
        await reindex_dependents(project_name, entity_type, changed_ids, batch_size)
    return total


async def backfill(project_name: str, *, batch_size: int = 10000) -> dict[str, int]:
    """Index everything which is missing or outdated in the project."""
    return {
        entity_type: await index_entities(
            project_name, entity_type, batch_size=batch_size
        )
        for entity_type in ENTITY_TYPES
    }
