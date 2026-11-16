__all__ = ["search"]

from typing import Any

from ayon_server.lib.postgres import Postgres

MAX_TERMS = 8

# Entity links of every hit are resolved for the top hits only.
QUERY = """
WITH hits AS (
    SELECT s.*, ts_rank(s.search_vector, {tsquery}) AS rank
    FROM entity_search s
    WHERE s.search_vector @@ ({tsquery})
    AND ($1::text[] IS NULL OR s.entity_type = ANY($1))
    ORDER BY rank DESC, s.updated_at DESC NULLS LAST
    LIMIT $2
)
SELECT
    h.entity_type, h.entity_id, h.rank,
    h.folder_id, f.name AS folder_name, f.label AS folder_label,
    f.folder_type, hi.path AS folder_path,
    h.task_id, t.name AS task_name, t.label AS task_label, t.task_type,
    h.product_id, p.name AS product_name, p.product_type,
    h.version_id, v.version,
    a.body, a.data->>'author' AS author, a.created_at
FROM hits h
JOIN folders f ON f.id = h.folder_id
JOIN hierarchy hi ON hi.id = h.folder_id
LEFT JOIN tasks t ON t.id = h.task_id
LEFT JOIN products p ON p.id = h.product_id
LEFT JOIN versions v ON v.id = h.version_id
LEFT JOIN activities a ON a.id = h.activity_id
ORDER BY h.rank DESC, h.updated_at DESC NULLS LAST
"""


def _lexeme(term: str) -> str:
    """Return the term as a quoted tsquery prefix lexeme."""
    escaped = term.lower().replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}':*"


async def search(
    project_name: str,
    text: str,
    *,
    entity_types: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the best matches for all whitespace-separated terms of the text.

    Every term is a prefix. It matches either literally (names are stored
    as one lexeme) or as the parser splits it (labels, descriptions, comments).
    """
    lexemes = [_lexeme(term) for term in text.split()[:MAX_TERMS]]
    if not lexemes:
        return []

    # $1 = entity types, $2 = limit, $3.. = terms
    tsquery = " && ".join(
        f"(${i}::text::tsquery || to_tsquery('simple', ${i}::text))"
        for i in range(3, len(lexemes) + 3)
    )
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        rows = await Postgres.fetch(
            QUERY.format(tsquery=tsquery), entity_types or None, limit, *lexemes
        )
    return [dict(row) for row in rows]
