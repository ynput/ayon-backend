"""Populate the per-project `entity_search` table.

Every entity type has a source: a SELECT returning its search rows
(entity_id, folder_id, task_id, product_id, version_id, literals,
attributes, search_vector, updated_at). A row is indexed when it is missing
or its `updated_at` differs from the source, so the same code serves the
backfill, the repair sweep and single updates.

The folder path is not stored: the search matches it in
`exported_attributes`, so renaming or moving a folder changes no rows.
The links follow moved parents and version literals contain the product
name: when a task, product or version row's folder, product or literals
change, the rows below it are marked outdated (`updated_at = NULL`) and
indexed again.
"""

__all__ = ["ENTITY_TYPES", "backfill", "index_entities"]

from typing import Any

from ayon_server.helpers.hierarchy_cache import AYON_INTERNAL_FOLDER_NAME
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

ENTITY_TYPES = ["folder", "task", "product", "version", "comment"]  # parents first

#
# Expressions building the documents
#


def text_vector(expr: str, weight: str) -> str:
    """Return a tsvector of the words of a text, matching from word starts.

    Tokens are indexed whole ("camel_case", "render.exr") and split on
    punctuation ("camel", "case", "render", "exr"). Underscores become hyphens:
    the parser keeps hyphenated words whole and also splits them. Accents are
    removed (on the query side too). The weight is the search tier:
    A = names, B = descriptions and comments, C = task assignees and
    comment authors (user names).
    """
    text = f"public.unaccent(coalesce({expr}, ''))"
    whole = f"to_tsvector('simple', translate({text}, '_', '-'))"
    parts = f"to_tsvector('simple', regexp_replace({text}, '[^[:alnum:]]+', ' ', 'g'))"
    return f"setweight({whole} || {parts}, '{weight}')"


def literal_text(*exprs: str) -> str:
    """Return the names and labels: not split, matched anywhere."""
    return f"lower(public.unaccent(concat_ws(' ', {', '.join(exprs)})))"


def name_vector(*exprs: str) -> str:
    """Return a tsvector of the own names, labels and types (not the path)."""
    return text_vector(f"concat_ws(' ', {', '.join(exprs)})", "A")


def description_vector() -> str:
    """Return a tsvector of the description of `e`: prose, matched by words."""
    return text_vector("e.attrib->>'description'", "B")


def attribute_text(entity_type: str) -> str:
    """Return the free-text attributes of `e` but the description.

    They hold codes and paths rather than prose, so like the literals they
    are not split and are matched anywhere. Free-text attributes are strings
    without an enum. Their names are part of the query: they come from the
    attribute definitions, which rarely change.
    """
    # Imported here: the entities import the indexer to enqueue their saves
    from ayon_server.entities.core.attrib import attribute_library

    attributes = [
        f"e.attrib->>'{attr['name']}'"
        for attr in attribute_library[entity_type]
        if attr.get("type") == "string"
        and attr["name"] != "description"  # see description_vector
        and attr["name"].isalnum()  # always true, but it is inlined into SQL
        and not attr.get("enum")
        and not attr.get("enumResolver")
    ]
    if not attributes:
        return "NULL"
    return f"nullif({literal_text(*attributes)}, '')"


#
# Sources
#

# Folders joined by the sources. The internal folder is hidden in the app,
# so nothing below it is indexed.
INDEXED_FOLDERS_CTE = f"""
    WITH RECURSIVE indexed_folders AS (
        SELECT id FROM folders
        WHERE parent_id IS NULL AND name <> '{AYON_INTERNAL_FOLDER_NAME}'
        UNION ALL
        SELECT f.id FROM folders f JOIN indexed_folders i ON f.parent_id = i.id
    )
"""


def get_folder_source() -> str:
    return f"""
        SELECT e.id, e.id, NULL::uuid, NULL::uuid, NULL::uuid,
            {literal_text("e.name", "e.label")},
            {attribute_text("folder")},
            {name_vector("e.name", "e.label")}
            || {description_vector()},
            e.updated_at
        FROM folders e
        JOIN indexed_folders i ON i.id = e.id
    """


def get_task_source() -> str:
    return f"""
        SELECT e.id, e.folder_id, e.id, NULL::uuid, NULL::uuid,
            {literal_text("e.name", "e.label", "e.task_type")},
            {attribute_text("task")},
            {name_vector("e.name", "e.label", "e.task_type")}
            || {description_vector()}
            || {text_vector("array_to_string(e.assignees, ' ')", "C")},
            e.updated_at
        FROM tasks e
        JOIN indexed_folders i ON i.id = e.folder_id
    """


def get_product_source() -> str:
    return f"""
        SELECT e.id, e.folder_id, NULL::uuid, e.id, NULL::uuid,
            {literal_text("e.name")},
            {attribute_text("product")},
            {name_vector("e.name")}
            || {description_vector()},
            e.updated_at
        FROM products e
        JOIN indexed_folders i ON i.id = e.folder_id
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
            {literal_text("p.name", version_name)},
            {attribute_text("version")},
            {name_vector(version_name)}
            || {description_vector()},
            e.updated_at
        FROM versions e
        JOIN products p ON p.id = e.product_id
        JOIN indexed_folders i ON i.id = p.folder_id
    """


def get_comment_source() -> str:
    """One row per comment, linked to the entity it is on.

    Comments on deleted or unsupported entities resolve to no folder and are
    skipped, as are those in the internal folder. No literals: they would
    rank every comment of a folder above its tasks. Markdown link targets
    are stripped, link texts are kept.
    """
    body = r"regexp_replace(e.body, '\]\([^)]*\)', ' ', 'g')"
    return f"""
        SELECT e.id, COALESCE(t.folder_id, p.folder_id, f.id), t.id, p.id, v.id,
            NULL, NULL,
            {text_vector(body, "B")} || {text_vector("e.data->>'author'", "C")},
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
        JOIN indexed_folders i ON i.id = COALESCE(t.folder_id, p.folder_id, f.id)
        WHERE e.activity_type = 'comment'
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
    query = f"""
        {INDEXED_FOLDERS_CTE}
        INSERT INTO entity_search (
            entity_id, folder_id, task_id, product_id, version_id,
            literals, attributes, search_vector, updated_at, entity_type
        )
        SELECT src.*, '{entity_type}' FROM ({get_source(entity_type)}) AS src (
            entity_id, folder_id, task_id, product_id, version_id,
            literals, attributes, search_vector, updated_at
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
            attributes = EXCLUDED.attributes,
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

    A product's versions and comments get a new folder or product name,
    the comments of a task or version a new folder or product.
    Returns the marked rows.
    """
    return f"""
        UPDATE entity_search SET updated_at = NULL
        WHERE entity_id <> ALL($1) AND {entity_type}_id = ANY($1)
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
    # Nothing below a folder or a comment takes values from its row
    if entity_ids is None or entity_type in ("folder", "comment"):
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
