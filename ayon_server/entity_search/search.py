__all__ = ["search"]

from typing import Any

from ayon_server.lib.postgres import Postgres

MAX_TERMS = 8

# Entity links of every hit are resolved for the top hits only.
# A hit in the literals (names, labels) scores 1 to 2 per term, so it outranks
# any hit in the texts. The closer the term is to a whole word of the literals,
# the higher the score; among equal scores, the shortest literals win.
# For similar matches, folders come first, then tasks, products and versions.
QUERY = """
WITH hits AS (
    SELECT s.*, hi.path AS folder_path,
        -- 32: rank / (rank + 1), so long texts (file lists) score below 1
        ({literal_hits} + ts_rank(s.search_vector, {tsquery}, 32))
        * CASE s.entity_type
            WHEN 'task' THEN 0.9
            WHEN 'product' THEN 0.8
            WHEN 'version' THEN 0.7
            ELSE 1
        END AS rank
    FROM entity_search s
    JOIN hierarchy hi ON hi.id = s.folder_id
    LEFT JOIN tasks t ON t.id = s.task_id
    WHERE {conditions}
    AND ($1::text[] IS NULL OR s.entity_type = ANY($1))
    {access}
    ORDER BY rank DESC, length(s.literals) NULLS LAST, s.updated_at DESC NULLS LAST
    LIMIT $2
)
SELECT
    h.entity_type, h.entity_id, h.rank,
    h.folder_id, f.name AS folder_name, f.label AS folder_label,
    f.folder_type, h.folder_path,
    h.task_id, t.name AS task_name, t.label AS task_label, t.task_type,
    h.product_id, p.name AS product_name, p.product_type,
    h.version_id, v.version,
    a.body, a.data->>'author' AS author, a.created_at
FROM hits h
JOIN folders f ON f.id = h.folder_id
LEFT JOIN tasks t ON t.id = h.task_id
LEFT JOIN products p ON p.id = h.product_id
LEFT JOIN versions v ON v.id = h.version_id
LEFT JOIN activities a ON a.id = h.activity_id
ORDER BY h.rank DESC, length(h.literals) NULLS LAST, h.updated_at DESC NULLS LAST
"""


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

    A term matches anywhere in the literals (names, labels),
    or the beginning of a word in the other texts. Accents are ignored.

    `folder_access` limits the rows to folder paths (LIKE patterns),
    `task_access` limits the rows of tasks and their comments to folder
    paths, or to tasks assigned to the given user. None means no limit.
    """
    terms = text.split()[:MAX_TERMS]
    if not terms:
        return []

    # $1 = entity types, $2 = limit, then the term, its pattern and lexeme
    args: list[Any] = [entity_types or None, limit]
    likes, similarities, tsqueries = [], [], []
    for term in terms:
        args += [term, like_pattern(term), prefix_lexeme(term)]
        term_arg, like_arg, lexeme_arg = (
            f"${i}::text" for i in range(len(args) - 2, len(args) + 1)
        )
        likes.append(f"s.literals LIKE lower(public.unaccent({like_arg}))")
        similarities.append(
            f"public.word_similarity(lower(public.unaccent({term_arg})), s.literals)"
        )
        # Underscores become hyphens, as in the index (see indexer.text_vector)
        tsqueries.append(
            f"to_tsquery('simple', translate(public.unaccent({lexeme_arg}), '_', '-'))"
        )

    access = []
    if folder_access is not None:
        args.append(folder_access)
        access.append(f"AND hi.path LIKE ANY(${len(args)}::text[])")
    if task_access is not None:
        paths, assignee = task_access
        args += [paths, assignee]
        access.append(
            f"AND (s.task_id IS NULL OR hi.path LIKE ANY(${len(args) - 1}::text[])"
            f" OR ${len(args)}::text = ANY(t.assignees))"
        )

    query = QUERY.format(
        access="\n    ".join(access),
        literal_hits=" + ".join(
            f"CASE WHEN {like} THEN 1 + {similarity} ELSE 0 END"
            for like, similarity in zip(likes, similarities)
        ),
        tsquery=" && ".join(tsqueries),
        conditions=" AND ".join(
            f"({like} OR s.search_vector @@ {tsquery})"
            for like, tsquery in zip(likes, tsqueries)
        ),
    )
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        rows = await Postgres.fetch(query, *args)
    return [dict(row) for row in rows]
