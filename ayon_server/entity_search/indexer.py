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
indexed again, in the same statement.
"""

__all__ = [
    "ENTITY_TYPES",
    "backfill",
    "index_entities",
    "indexed_attributes",
    "mark_attributes_outdated",
]

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


def indexed_attributes() -> dict[str, list[str]]:
    """Return {entity type: names of the attributes in `attribute_text`}.

    Free-text attributes are strings without an enum, but the description.
    """
    # Imported here: the entities import the indexer to enqueue their saves
    from ayon_server.entities.core.attrib import attribute_library

    return {
        entity_type: [
            attr["name"]
            for attr in attribute_library[entity_type]
            if attr.get("type") == "string"
            and attr["name"] != "description"  # see description_vector
            and attr["name"].isalnum()  # always true, but it is inlined into SQL
            and not attr.get("enum")
            and not attr.get("enum_resolver")
        ]
        for entity_type in ("folder", "task", "product", "version")
    }


def attribute_text(entity_type: str) -> str:
    """Return the free-text attributes of `e` but the description.

    They hold codes and paths rather than prose, so like the literals they
    are not split and are matched anywhere. Their names are part of
    the query: they come from the attribute definitions, which rarely change.
    """
    attributes = [f"e.attrib->>'{name}'" for name in indexed_attributes()[entity_type]]
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
        " ELSE 'v' || lpad(e.version::text, greatest(3, length(e.version::text)), '0')"
        " END"
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


# Entities whose rows give values to the rows below them (see the module doc)
PARENT_TYPES = {"task", "product", "version"}


def build_upsert_query(entity_type: str) -> str:
    """Return the query indexing a batch of outdated rows.

    $1 = batch size, $2 = entity ids or NULL for all. Returns the number of
    indexed rows and the rows below moved or renamed entities, which the same
    statement marks outdated ("<entity type>:<entity id>"), so a lost queue
    or an interrupted run cannot leave them stale. All parts of the statement
    see the rows as they were before it (`old`).
    """
    columns = (
        "entity_id, folder_id, task_id, product_id, version_id,"
        " literals, attributes, search_vector, updated_at"
    )
    marked, dependents = "", "'{}'::text[]"
    if entity_type in PARENT_TYPES:
        marked = f"""
        , marked AS (
            UPDATE entity_search d SET updated_at = NULL
            FROM outdated o
            JOIN entity_search old ON old.entity_id = o.entity_id
            WHERE d.{entity_type}_id = o.entity_id AND d.entity_id <> o.entity_id
            AND (
                old.folder_id IS DISTINCT FROM o.folder_id
                OR old.product_id IS DISTINCT FROM o.product_id
                OR old.literals IS DISTINCT FROM o.literals
            )
            RETURNING d.entity_type, d.entity_id
        )"""
        dependents = "ARRAY(SELECT entity_type || ':' || entity_id FROM marked)"

    return f"""
        {INDEXED_FOLDERS_CTE},
        outdated AS (
            SELECT * FROM ({get_source(entity_type)}) AS src ({columns})
            WHERE NOT EXISTS (
                SELECT 1 FROM entity_search s
                WHERE s.entity_id = src.entity_id
                AND s.updated_at IS NOT DISTINCT FROM src.updated_at
            )
            AND ($2::uuid[] IS NULL OR src.entity_id = ANY($2))
            LIMIT $1
        ),
        upserted AS (
            INSERT INTO entity_search ({columns}, entity_type)
            SELECT {columns}, '{entity_type}' FROM outdated
            ON CONFLICT (entity_id) DO UPDATE SET
                folder_id = EXCLUDED.folder_id,
                task_id = EXCLUDED.task_id,
                product_id = EXCLUDED.product_id,
                version_id = EXCLUDED.version_id,
                literals = EXCLUDED.literals,
                attributes = EXCLUDED.attributes,
                search_vector = EXCLUDED.search_vector,
                updated_at = EXCLUDED.updated_at
            RETURNING 1
        )
        {marked}
        SELECT (SELECT count(*) FROM upserted) AS indexed, {dependents} AS dependents
    """


#
# Indexing
#


async def index_entities(
    project_name: str,
    entity_type: str,
    entity_ids: list[str] | None = None,
    *,
    batch_size: int = 10000,
) -> int:
    """Index missing or outdated rows of one entity type (all without ids).

    Batches are committed one at a time. The rows below moved or renamed
    entities are indexed again afterwards. Returns the number of indexed
    rows of the type.
    """
    query = build_upsert_query(entity_type)
    total = 0
    dependents: dict[str, list[str]] = {}
    while True:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            row = await Postgres.fetchrow(query, batch_size, entity_ids, timeout=600)
        total += row["indexed"]
        for dependent in row["dependents"]:
            dependent_type, dependent_id = dependent.split(":")
            dependents.setdefault(dependent_type, []).append(dependent_id)
        if row["indexed"] < batch_size:
            break
        logger.debug(f"[{project_name}] Indexed {total} {entity_type}s for search")

    for dependent_type in ENTITY_TYPES:  # versions before their comments
        if ids := dependents.get(dependent_type):
            await index_entities(
                project_name, dependent_type, ids, batch_size=batch_size
            )
    return total


async def backfill(project_name: str, *, batch_size: int = 10000) -> dict[str, int]:
    """Index everything which is missing or outdated in the project.

    Rows of entities moved under the internal folder are removed first.
    """
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        await Postgres.execute(
            f"""
            {INDEXED_FOLDERS_CTE}
            DELETE FROM entity_search
            WHERE folder_id NOT IN (SELECT id FROM indexed_folders)
            """,
            timeout=600,
        )
    return {
        entity_type: await index_entities(
            project_name, entity_type, batch_size=batch_size
        )
        for entity_type in ENTITY_TYPES
    }


async def mark_attributes_outdated(before: dict[str, list[str]]) -> None:
    """Mark the rows outdated whose indexed attributes changed.

    `before` = `indexed_attributes()` before the attribute definitions changed.
    The rows are indexed again by the next sweep.
    """
    from ayon_server.helpers.project_list import get_project_list

    after = indexed_attributes()
    if not (types := [t for t in after if after[t] != before.get(t)]):
        return
    for project in await get_project_list():
        await Postgres.execute(
            f"""
            UPDATE project_{project.name}.entity_search SET updated_at = NULL
            WHERE entity_type = ANY($1)
            """,
            types,
        )
