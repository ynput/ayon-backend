__all__ = ["build_search_cte", "search"]

from typing import Any

from ayon_server.lib.postgres import Postgres

MAX_TERMS = 8

# A hit in the literals (path, names, labels) scores 1 to 2 per term, so it
# outranks any hit in the texts (normalized to 0-1). The closer the term is
# to a whole word of the literals, the higher the score; among equal scores,
# the shortest literals win. For similar matches, folders come first,
# then tasks, products and versions.
SEARCH_CTE = """
    SELECT s.*, hi.path AS folder_path,
        ({literal_hits} + ts_rank(s.search_vector, {tsquery}, 32))
        * CASE s.entity_type
            WHEN 'task' THEN 0.9
            WHEN 'product' THEN 0.8
            WHEN 'version' THEN 0.7
            ELSE 1
        END AS rank
    FROM {schema}.entity_search s
    JOIN {schema}.hierarchy hi ON hi.id = s.folder_id
    LEFT JOIN {schema}.tasks t ON t.id = s.task_id
    WHERE {conditions}
    {filters}
    {top}
"""

# Entity links are resolved for the top hits only
SEARCH_QUERY = """
    WITH hits AS ({search_cte})
    SELECT
        h.entity_type, h.entity_id, h.rank,
        h.folder_id, f.name AS folder_name, f.label AS folder_label,
        f.folder_type, h.folder_path,
        h.task_id, t.name AS task_name, t.label AS task_label, t.task_type,
        h.product_id, p.name AS product_name, p.product_type,
        h.version_id, v.version,
        a.body, a.data->>'author' AS author, a.created_at
    FROM hits h
    JOIN {schema}.folders f ON f.id = h.folder_id
    LEFT JOIN {schema}.tasks t ON t.id = h.task_id
    LEFT JOIN {schema}.products p ON p.id = h.product_id
    LEFT JOIN {schema}.versions v ON v.id = h.version_id
    LEFT JOIN {schema}.activities a ON a.id = h.activity_id
    ORDER BY h.rank DESC, length(h.literals) NULLS LAST, h.updated_at DESC NULLS LAST
"""


def sql_string(value: str) -> str:
    """Return the value as an SQL string literal.

    Relies on standard_conforming_strings (the default): backslashes are
    literal, only quotes are doubled. Postgres text cannot hold NUL.
    """
    return "'" + value.replace("\x00", "").replace("'", "''") + "'"


def sql_string_array(values: list[str]) -> str:
    return f"ARRAY[{', '.join(map(sql_string, values))}]::text[]"


def like_pattern(term: str) -> str:
    """Return a LIKE pattern matching the term at any position.

    Names are full of underscores, which LIKE would take as wildcards.
    """
    for char in "\\%_":
        term = term.replace(char, f"\\{char}")
    return f"%{term}%"


def prefix_lexeme(term: str) -> str:
    """Return the term as a quoted tsquery lexeme matching word prefixes."""
    escaped = term.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}':*"


def build_search_cte(
    project_name: str,
    text: str,
    *,
    entity_types: list[str] | None = None,
    limit: int | None = 50,
    folder_access: list[str] | None = None,
    task_access: tuple[list[str], str | None] | None = None,
) -> str | None:
    """Return a query selecting the best search hits, without arguments.

    The rows are the `entity_search` rows with `folder_path` and `rank`.
    A term matches anywhere in the literals (path, names, labels), or the
    beginning of a word in the other texts. All terms must match.
    Accents are ignored. Returns None when the text has no terms.

    `folder_access` limits the rows to folder paths (LIKE patterns),
    `task_access` limits the rows of tasks and their comments to folder
    paths, or to tasks assigned to the given user. None means no limit.
    With `limit=None`, all hits are returned unordered (to filter by them).
    """
    terms = text.split()[:MAX_TERMS]
    if not terms:
        return None

    literal_hits, tsqueries, conditions = [], [], []
    for term in terms:
        term_value = f"lower(public.unaccent({sql_string(term)}))"
        pattern = f"lower(public.unaccent({sql_string(like_pattern(term))}))"
        # Underscores become hyphens, as in the index (see indexer.text_vector)
        lexeme = (
            f"translate(public.unaccent({sql_string(prefix_lexeme(term))}), '_', '-')"
        )

        like = f"s.literals LIKE {pattern}"
        tsquery = f"to_tsquery('simple', {lexeme})"
        similarity = f"public.word_similarity({term_value}, s.literals)"
        literal_hits.append(f"CASE WHEN {like} THEN 1 + {similarity} ELSE 0 END")
        tsqueries.append(tsquery)
        conditions.append(f"({like} OR s.search_vector @@ {tsquery})")

    filters = []
    if entity_types:
        filters.append(f"AND s.entity_type = ANY({sql_string_array(entity_types)})")
    if folder_access is not None:
        filters.append(f"AND hi.path LIKE ANY({sql_string_array(folder_access)})")
    if task_access is not None:
        paths, assignee = task_access
        assigned = f"OR {sql_string(assignee)} = ANY(t.assignees)" if assignee else ""
        filters.append(
            f"AND (s.task_id IS NULL OR hi.path LIKE ANY({sql_string_array(paths)})"
            f" {assigned})"
        )

    return SEARCH_CTE.format(
        schema=f"project_{project_name}",
        literal_hits=" + ".join(literal_hits),
        tsquery=" && ".join(tsqueries),
        conditions=" AND ".join(conditions),
        filters="\n    ".join(filters),
        top=""
        if limit is None
        else (
            "ORDER BY rank DESC, length(s.literals) NULLS LAST,"
            f" s.updated_at DESC NULLS LAST LIMIT {int(limit)}"
        ),
    )


async def search(
    project_name: str,
    text: str,
    *,
    entity_types: list[str] | None = None,
    limit: int = 50,
    folder_access: list[str] | None = None,
    task_access: tuple[list[str], str | None] | None = None,
) -> list[dict[str, Any]]:
    """Return the best matches for all whitespace-separated terms of the text.

    See `build_search_cte` for the arguments.
    """
    cte = build_search_cte(
        project_name,
        text,
        entity_types=entity_types,
        limit=limit,
        folder_access=folder_access,
        task_access=task_access,
    )
    if not cte:
        return []

    query = SEARCH_QUERY.format(search_cte=cte, schema=f"project_{project_name}")
    rows = await Postgres.fetch(query)
    return [dict(row) for row in rows]
