"""Backwards compatibility for typed `attrib` selections.

The `attrib` field of the entity nodes used to be a typed object with a field
per attribute. Queries of older clients (e.g. ayon-python-api < 1.2.16)
select attributes explicitly:

    folders { edges { node { id attrib { fps resolutionWidth } } } }

`attrib` is now a JSON field, so such a query would not be valid.
Before the query is parsed, the selections are rewritten to

    attrib(legacySelection: "fps resolutionWidth")

which returns an object with the same shape as the typed field did
(aliases and `__typename` included).

Only flat selections are rewritten (fields, aliases, `__typename`).
Selections with fragments or directives are left as they are
and fail validation.
"""

import re
from collections.abc import Iterator

from strawberry.extensions import SchemaExtension

from ayon_server.logging import logger

# `attrib { ... }` with a flat selection (no nested braces).
# The lookbehind ensures `ownAttrib`, `allAttrib`... are not matched
LEGACY_ATTRIB_SELECTION = re.compile(r"(?<![_0-9A-Za-z])attrib(\s*)\{([^{}]*)\}")

# `name` or `alias: name` separated by whitespace or commas
SELECTION_ITEM = re.compile(
    r"([_A-Za-z][_0-9A-Za-z]*)(?:\s*:\s*([_A-Za-z][_0-9A-Za-z]*))?"
)
SELECTION_SEPARATOR = re.compile(r"[\s,]*")


def _parse_selection(selection: str) -> list[str] | None:
    items: list[str] = []
    pos = 0
    while True:
        pos = SELECTION_SEPARATOR.match(selection, pos).end()  # type: ignore[union-attr]
        if pos >= len(selection):
            break
        match = SELECTION_ITEM.match(selection, pos)
        if match is None:
            return None  # Fragments, directives, comments... not supported
        alias, name = match.groups()
        items.append(f"{alias}:{name}" if name else alias)
        pos = match.end()
    return items


def rewrite_legacy_attrib_selections(query: str) -> tuple[str, int]:
    """Rewrite `attrib { a b: c }` to `attrib(legacySelection: "a b:c")`

    Returns the new query and the number of rewritten selections.
    """
    if "attrib" not in query:
        return query, 0

    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        items = _parse_selection(match.group(2))
        if items is None:
            return match.group(0)
        count += 1
        # A single string: arguments are parsed for every node, lists are slower
        return f'attrib(legacySelection: "{" ".join(items)}")'

    return LEGACY_ATTRIB_SELECTION.sub(replace, query), count


class LegacyAttribSelection(SchemaExtension):
    """Rewrite typed `attrib` selections of older clients before parsing."""

    def on_parse(self) -> Iterator[None]:
        ctx = self.execution_context
        if ctx.query and ctx.graphql_document is None:
            query, count = rewrite_legacy_attrib_selections(ctx.query)
            if count:
                ctx.query = query
                user_agent = None
                if isinstance(ctx.context, dict) and (
                    req := ctx.context.get("request")
                ):
                    user_agent = req.headers.get("user-agent")
                logger.debug(
                    f"Rewrote {count} legacy attrib selection(s) "
                    f"in {ctx.operation_name or 'unnamed'} query "
                    f"(user agent: {user_agent})"
                )
        yield
