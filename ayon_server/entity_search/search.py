__all__ = ["build_search_cte", "search"]

import re
from typing import Any

from ayon_server.lib.postgres import Postgres

MAX_TERMS = 8
MIN_TERM_LENGTH = 2  # shorter terms match nearly everything
MIN_INFIX_LENGTH = 3  # shorter patterns cannot use the trigram index
MAX_INLINED_FOLDERS = 10000  # longer folder lists are not inlined into the query

# Every term scores by where it matches the beginning of a word: 3 in the
# names (weight A), 2 in descriptions and comments (B), 1 in user names (C),
# otherwise by where it matches anywhere: at most 0.5 in the literals (names,
# labels), 0.25 in the folder path (not for comments) or the free-text
# attributes (constant: word_similarity of long texts is slow on common
# terms). The scores are averaged over the terms. Within a tier, folders
# come first, then tasks, products and versions; among equal scores,
# the shortest literals win.
SEARCH_CTE = """
    SELECT s.*, hi.path AS folder_path,
        {score}
        + CASE s.entity_type
            WHEN 'task' THEN 0.2
            WHEN 'product' THEN 0.1
            WHEN 'version' THEN 0
            ELSE 0.3
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


def parse_query(text: str) -> list[list[str]]:
    """Return the term groups of a search text: comma = OR, space = AND.

    Terms are split on characters other than letters, digits and `_-./`
    (so "bob's" finds "bob" and "sh:*" is "sh"), short terms are dropped.
    """
    groups, count = [], 0
    for part in text.split(","):
        terms = [
            term
            for term in re.split(r"[^\w./-]+", part)
            if len(term) >= MIN_TERM_LENGTH
        ][: MAX_TERMS - count]
        if terms:
            groups.append(terms)
            count += len(terms)
    return groups


async def get_path_folders(schema: str, term: str) -> str | None:
    """Return the folders whose path contains the term, as an SQL array.

    The ids are inlined: Postgres hashes a constant array, while it would
    scan an array from a subquery for every row. Folder names are ASCII,
    so the path needs no unaccent and ILIKE can use the trigram index.
    Returns None when no folder matches.
    """
    query = f"""
        SELECT folder_id FROM {schema}.exported_attributes
        WHERE path ILIKE lower(public.unaccent($1))
    """
    rows = await Postgres.fetch(query, like_pattern(term))
    if not rows:
        return None
    if len(rows) > MAX_INLINED_FOLDERS:
        # shortcut: slow for broad terms, but keeps the query size bounded
        return f"ARRAY({query.replace('$1', sql_string(like_pattern(term)))})"
    return f"'{{{','.join(str(row['folder_id']) for row in rows)}}}'::uuid[]"


def build_term(term: str, path_folders: str | None) -> tuple[str, str]:
    """Return the score and the condition of one term.

    `path_folders` are the folders whose path contains the term
    (see `get_path_folders`).
    """
    # Underscores become hyphens, as in the index (see indexer.text_vector)
    lexeme = f"translate(public.unaccent({sql_string(prefix_lexeme(term))}), '_', '-')"
    tsquery = f"to_tsquery('simple', {lexeme})"
    vector_score = (
        f"WHEN s.search_vector @@ to_tsquery('simple', {lexeme} || 'A') THEN 3"
        f" WHEN s.search_vector @@ to_tsquery('simple', {lexeme} || 'B') THEN 2"
        f" WHEN s.search_vector @@ {tsquery} THEN 1"
    )
    if len(term) < MIN_INFIX_LENGTH:
        return f"CASE {vector_score} ELSE 0 END", f"s.search_vector @@ {tsquery}"

    term_value = f"lower(public.unaccent({sql_string(term)}))"
    pattern = f"lower(public.unaccent({sql_string(like_pattern(term))}))"
    like = f"s.literals LIKE {pattern}"
    similarity = f"public.word_similarity({term_value}, s.literals)"
    attr_like = f"s.attributes LIKE {pattern}"
    infix = attr_like
    if path_folders:
        # ANY keeps it an index condition on entity_search (folder_id)
        path_match = (
            f"(s.entity_type <> 'comment' AND s.folder_id = ANY({path_folders}))"
        )
        infix = f"{path_match} OR {attr_like}"
    score = (
        f"CASE {vector_score} WHEN {like} THEN 0.5 * {similarity}"
        f" WHEN {infix} THEN 0.25 ELSE 0 END"
    )
    return score, f"({like} OR {infix} OR s.search_vector @@ {tsquery})"


async def build_search_cte(
    project_name: str,
    text: str,
    *,
    entity_types: list[str] | None = None,
    limit: int | None = 50,
    folder_access: list[str] | None = None,
    task_access: tuple[list[str], str | None] | None = None,
    comment_categories: list[str] | None = None,
) -> str | None:
    """Return a query selecting the best search hits, without arguments.

    The rows are the `entity_search` rows with `folder_path` and `rank`.
    A term matches the beginning of a word, or (3+ characters) anywhere in
    the literals (names, labels), the folder path (not for comments) and
    the free-text attributes other than the description. All terms of a
    group must match, any group may (see `parse_query`). Accents are ignored.
    Returns None when the text has no terms.

    `folder_access` limits the rows to folder paths (LIKE patterns),
    `task_access` limits the rows of tasks and their comments to folder
    paths, or to tasks assigned to the given user, `comment_categories`
    limits the comments to these categories and uncategorized ones.
    None means no limit.
    With `limit=None`, all hits are returned unordered (to filter by them).
    """
    groups = parse_query(text)
    if not groups:
        return None

    schema = f"project_{project_name}"
    path_folders = {
        term: await get_path_folders(schema, term)
        for term in {term for terms in groups for term in terms}
        if len(term) >= MIN_INFIX_LENGTH
    }
    group_scores, group_conditions = [], []
    for terms in groups:
        scores, conditions = zip(
            *(build_term(term, path_folders.get(term)) for term in terms)
        )
        group_scores.append(f"({' + '.join(scores)}) / {len(terms)}")
        group_conditions.append(f"({' AND '.join(conditions)})")

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

    if comment_categories is not None:
        filters.append(
            f"AND (s.activity_id IS NULL OR EXISTS (SELECT 1 FROM {schema}.activities a"
            " WHERE a.id = s.activity_id AND (a.data->>'category' IS NULL"
            f" OR a.data->>'category' = ANY({sql_string_array(comment_categories)}))))"
        )

    return SEARCH_CTE.format(
        schema=schema,
        score=f"GREATEST({', '.join(group_scores)})",
        # Parenthesized: the access filters below must apply to every group
        conditions=f"({' OR '.join(group_conditions)})",
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
    comment_categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the best matches for all whitespace-separated terms of the text.

    See `build_search_cte` for the arguments.
    """
    cte = await build_search_cte(
        project_name,
        text,
        entity_types=entity_types,
        limit=limit,
        folder_access=folder_access,
        task_access=task_access,
        comment_categories=comment_categories,
    )
    if not cte:
        return []

    query = SEARCH_QUERY.format(search_cte=cte, schema=f"project_{project_name}")
    rows = await Postgres.fetch(query)
    return [dict(row) for row in rows]
