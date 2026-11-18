"""Populate the per-project `entity_search` table.

Every statement indexes only rows which are missing or whose `updated_at`
differs from the source, so the same code serves the backfill, the repair
sweep and the single-entity update.
"""

__all__ = ["ENTITY_TYPES", "backfill", "get_source", "index_entities"]

from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

# Texts are unaccented on both sides (index and query), so "prilis" finds "příliš".


def _text(expr: str, whole: str, parts: str) -> str:
    """Words of a text. They match from the beginning of a word only.

    Every whitespace-separated token is indexed whole ("camel_case",
    "render.exr") with the `whole` weight, and split on punctuation
    ("camel", "case", "render", "exr") with the lower `parts` weight.
    The parser alone would split "a_b" only and keep "a.b" only.
    """
    text = f"lower(public.unaccent(coalesce({expr}, '')))"
    # Built as a literal: the parser would split the tokens, and lexemes
    # need positions to carry a weight. Longer tokens than 2046 bytes
    # are rejected by tsvector, the parser skips them too.
    tokens = f"""(
        SELECT setweight(coalesce(string_agg(
            '''' || replace(replace(tok, '\\', '\\\\'), '''', '''''')
            || ''':' || least(i, 16383), ' '
        ), '')::tsvector, '{whole}')
        FROM regexp_split_to_table({text}, '\\s+') WITH ORDINALITY AS w(raw, i),
        LATERAL regexp_replace(raw, '^[^[:alnum:]]+|[^[:alnum:]]+$', '', 'g') AS tok
        WHERE tok <> '' AND octet_length(tok) < 2047
    )"""
    split = (
        "setweight(to_tsvector('simple', "
        f"regexp_replace({text}, '[^[:alnum:]]+', ' ', 'g')), '{parts}')"
    )
    return f"({tokens} || {split})"


def _literals(*exprs: str) -> str:
    """Names and labels. They are not split and match from any position
    using the trigram index."""
    return f"lower(public.unaccent(concat_ws(' ', {', '.join(exprs)})))"


def _searchable_attributes(entity_type: str) -> list[str]:
    """Free-text attributes: strings without an enum."""
    # Imported here: the entities import the indexer to enqueue their saves
    from ayon_server.entities.core.attrib import attribute_library

    return [
        attr["name"]
        for attr in attribute_library[entity_type]
        if attr.get("type") == "string"
        and attr["name"] != "description"  # has its own, higher weight
        and not attr.get("enum")
        and not attr.get("enumResolver")
    ]


_UUID_NULL = "NULL::uuid"
_VERSION_NAME = (
    "CASE WHEN e.version < 0 THEN 'HERO' ELSE 'v' || lpad(e.version::text, 3, '0') END"
)

# Link columns (folder_id, task_id, product_id, version_id), the literals
# and the FROM clause of every entity type. The source row is aliased as `e`.
_ENTITIES: dict[str, tuple[str, str, str]] = {
    "folder": (
        f"e.id, {_UUID_NULL}, {_UUID_NULL}, {_UUID_NULL}",
        _literals("e.name", "e.label"),
        "folders e",
    ),
    "task": (
        f"e.folder_id, e.id, {_UUID_NULL}, {_UUID_NULL}",
        _literals("e.name", "e.label"),
        "tasks e",
    ),
    "product": (
        f"e.folder_id, {_UUID_NULL}, e.id, {_UUID_NULL}",
        _literals("e.name"),
        "products e",
    ),
    # task_id stays empty: the task which produced the version is a different
    # relation and would cascade-delete the row when the task is removed.
    "version": (
        f"p.folder_id, {_UUID_NULL}, e.product_id, e.id",
        _literals(_VERSION_NAME),
        "versions e JOIN products p ON p.id = e.product_id",
    ),
}

# One row per comment; the link columns point to the entity it is on.
# Comments on deleted or unsupported entities resolve to no folder
# and are skipped. Link targets are stripped, link texts are kept.
_COMMENT_COLUMNS = f"""
    e.id, COALESCE(t.folder_id, p.folder_id, f.id), t.id, p.id, v.id,
    NULL,
    {_text(r"regexp_replace(e.body, '\]\([^)]*\)', ' ', 'g')", "B", "C")},
    e.updated_at
"""
_COMMENT_SOURCE = """
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
"""

ENTITY_TYPES = [*_ENTITIES, "comment"]

# A moved task, product or version takes the rows linked to it along
# (its versions and comments). $1 = ids, or NULL for all.
_RELINK = {
    "task": """
        UPDATE entity_search s SET folder_id = e.folder_id FROM tasks e
        WHERE s.task_id = e.id AND s.folder_id <> e.folder_id
        AND ($1::uuid[] IS NULL OR e.id = ANY($1))
    """,
    "product": """
        UPDATE entity_search s SET folder_id = e.folder_id FROM products e
        WHERE s.product_id = e.id AND s.folder_id <> e.folder_id
        AND ($1::uuid[] IS NULL OR e.id = ANY($1))
    """,
    "version": """
        UPDATE entity_search s
        SET product_id = e.product_id, folder_id = p.folder_id
        FROM versions e JOIN products p ON p.id = e.product_id
        WHERE s.version_id = e.id
        AND (s.product_id <> e.product_id OR s.folder_id <> p.folder_id)
        AND ($1::uuid[] IS NULL OR e.id = ANY($1))
    """,
}


def get_source(entity_type: str) -> tuple[str, str, list[Any]]:
    """Return the select list, the FROM clause and the extra query arguments.

    The select list is (id, folder_id, task_id, product_id, version_id,
    literals, search_vector, updated_at). Extra arguments start at $3.
    The searchable attributes follow the current attribute definitions.
    """
    if entity_type == "comment":
        return _COMMENT_COLUMNS, _COMMENT_SOURCE, []

    links, literals, source = _ENTITIES[entity_type]
    attributes = """(
        SELECT string_agg(value, ' ') FROM jsonb_each_text(e.attrib)
        WHERE key = ANY($3::text[])
    )"""
    columns = f"""
        e.id, {links},
        {literals},
        {_text("e.attrib->>'description'", "B", "C")}
        || {_text(attributes, "C", "D")},
        e.updated_at
    """
    return columns, source, [_searchable_attributes(entity_type)]


def _build_query(entity_type: str) -> tuple[str, list[Any]]:
    columns, source, args = get_source(entity_type)
    where = "WHERE" if "WHERE" not in source else "AND"
    query = f"""
        INSERT INTO entity_search (
            entity_id, folder_id, task_id, product_id, version_id,
            literals, search_vector, updated_at, entity_type
        )
        SELECT {columns}, '{entity_type}'
        FROM {source}
        {where} NOT EXISTS (
            SELECT 1 FROM entity_search s
            WHERE s.entity_id = e.id
            AND s.updated_at IS NOT DISTINCT FROM e.updated_at
        )
        AND ($2::uuid[] IS NULL OR e.id = ANY($2))
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
    return query, args


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
    query, extra_args = _build_query(entity_type)
    args = [batch_size, entity_ids, *extra_args]
    total = 0
    while True:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            status = await Postgres.execute(query, *args, timeout=600)
        count = int(status.split()[-1])  # "INSERT 0 <count>"
        total += count
        if count < batch_size:
            break
        logger.debug(f"[{project_name}] Indexed {total} {entity_type}s for search")

    if entity_type in _RELINK:
        async with Postgres.transaction():
            await Postgres.set_project_schema(project_name)
            await Postgres.execute(_RELINK[entity_type], entity_ids, timeout=600)
    return total


async def backfill(project_name: str, *, batch_size: int = 10000) -> dict[str, int]:
    """Index everything which is missing or outdated in the project."""
    return {
        entity_type: await index_entities(
            project_name, entity_type, batch_size=batch_size
        )
        for entity_type in ENTITY_TYPES
    }
