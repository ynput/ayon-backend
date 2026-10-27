import re
from base64 import b64decode, b64encode
from collections.abc import Sequence
from typing import Any, NamedTuple

from ayon_server.exceptions import BadRequestException
from ayon_server.utils import json_dumps, json_loads

# Top-level non-nullable fields.
# We don't need COALESCE for these.
COLUMN_TYPES = {
    "id": "text",
    "name": "text",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
    "status": "text",
    "creation_order": "numeric",
    "path": "text",
}


def decode_cursor(cursor: str | None) -> list[Any]:
    if not cursor:
        return []
    try:
        cur = json_loads(b64decode(cursor).decode())
        if not isinstance(cur, list):
            raise BadRequestException("Cursor must decode to a list")
        return cur
    except Exception:
        raise BadRequestException("Invalid cursor")


def encode_cursor(decoded_cursor: list[Any]) -> str:
    return b64encode(json_dumps(decoded_cursor).encode()).decode()


MAX_SORT_KEYS = 5


class SortKey(NamedTuple):
    name: str
    descending: bool = False


def get_sort_keys(sort_by: str | list[str] | None) -> list[SortKey]:
    """Normalize the `sortBy` argument to a list of unique sort keys.

    A key prefixed with `-` is sorted in descending order (`+` is
    accepted for ascending order). A single string is accepted
    for backwards compatibility.
    """
    if not sort_by:
        return []
    if isinstance(sort_by, str):
        sort_by = [sort_by]

    keys: dict[str, SortKey] = {}
    for value in sort_by:
        descending = value.startswith("-")
        name = value.removeprefix("-") if descending else value.removeprefix("+")
        if not name:
            raise BadRequestException(f"Invalid sort key: '{value}'")
        # The first occurrence of a key wins, later ones would have no effect
        keys.setdefault(name, SortKey(name, descending))

    if len(keys) > MAX_SORT_KEYS:
        raise BadRequestException(f"sortBy accepts at most {MAX_SORT_KEYS} keys")
    return list(keys.values())


class SortColumn(NamedTuple):
    """A sorted SQL expression and its direction"""

    expression: str
    descending: bool = False


# Plain strings are sorted in ascending order
OrderBy = list[str | SortColumn]
OrderBySequence = Sequence[str | SortColumn]


def as_sort_column(column: str | SortColumn) -> SortColumn:
    return column if isinstance(column, SortColumn) else SortColumn(column)


def sort_columns(expressions: list[str], descending: bool) -> list[SortColumn]:
    """Return the expressions of a single sort key as sort columns"""
    return [SortColumn(expression, descending) for expression in expressions]


def with_tiebreakers(order_by: OrderBySequence, *columns: str) -> OrderBy:
    """Append the columns which are not already sorted by (in ascending order).

    Keyset pagination needs a unique ordering, otherwise rows sharing
    the same sort values may be skipped or repeated between pages.
    """
    sorted_by = {as_sort_column(c).expression for c in order_by}
    return [*order_by, *(c for c in columns if c not in sorted_by)]


def create_pagination(
    order_by: OrderBySequence,
    first: int | None = None,
    after: str | None = None,
    last: int | None = None,
    before: str | None = None,
) -> tuple[str, str, str]:
    """
    Generates a pagination SQL query for a GraphQL resolver.

    Accepts a list of columns to sort by and GraphQL pagination
    parameters (`after`, `before`, `first`, `last`).
    Columns are plain SQL expressions sorted in ascending order,
    or `SortColumn` items with their own direction.
    `last` reverses the whole ordering.

    Returns a tuple of three strings: `ordering`, `conditions`, and `cursor`.

    - `ordering`: The "ORDER BY" clause of the query,
        including the `ORDER BY` statement itself.
    - `conditions`: Conditions for the `WHERE` clause,
        meant to be combined with other conditions using `AND`.
    - `cursor`: A set of virtual columns in the `SELECT` section,
        which the resolver uses to construct the actual cursor.
    """

    columns = [as_sort_column(c) for c in order_by]
    cursor_arr = []
    ordering_arr = []
    decoded_cursor = decode_cursor(before or after)
    operator = "<" if before else ">"

    # One item per sorted column the cursor covers.
    # `key` is the expression compared with `value` (a SQL literal,
    # or None when the cursor value is NULL), `nullable` tells
    # whether the expression may evaluate to NULL and `operator`
    # is the comparison selecting the rows past the cursor.
    cursor_keys: list[CursorKey] = []
    for i in range(min(len(columns), len(decoded_cursor))):
        ob, descending = columns[i]
        val = decoded_cursor[i]
        col_operator = _flip(operator) if descending else operator
        col_name = ob.split(".")[-1]

        is_jsonb = ("->" in ob) and ("->>" not in ob) and ("::" not in ob)
        ctype = COLUMN_TYPES.get(col_name)

        if ctype and not is_jsonb:
            # Known non-nullable top-level field
            if ctype == "text":
                val_str = str(val).replace("'", "''") if val is not None else ""
                sql_val = f"'{val_str}'::text"
            elif ctype == "timestamptz":
                sql_val = f"'{val}'::timestamptz"
                if not isinstance(val, str) or not re.match(
                    r"^\d{4}-\d{2}-\d{2}T[0-9:\.\+\-Z]+$", val
                ):
                    raise BadRequestException(
                        f"Invalid value for timestamptz field: {val}"
                    )
            else:  # numeric
                if not isinstance(val, (int, float)):
                    raise BadRequestException(f"Invalid value for numeric field: {val}")
                sql_val = f"{val or 0}"
            cursor_keys.append(CursorKey(f"{ob}", sql_val, False, col_operator))
            continue

        # Nullable fields or JSONB
        if val is None:
            # The type does not matter, NULL is only tested with IS [NOT] NULL
            cursor_keys.append(CursorKey(f"({ob})", None, True, col_operator))
            continue

        if isinstance(val, (int, float)):
            cast = "numeric"
            sql_val = f"{val}::numeric"
        elif isinstance(val, str) and re.match(
            r"^\d{4}-\d{2}-\d{2}T[0-9:\.\+\-Z]+$", val
        ):
            cast = "timestamptz"
            sql_val = f"'{val}'::timestamptz"
        else:
            cast = "text"
            v_str = str(val).replace("'", "''")
            sql_val = f"'{v_str}'::text"

        cursor_keys.append(CursorKey(f"({ob})::{cast}", sql_val, True, col_operator))

    # Postgres puts NULLs last in ascending and first in descending order,
    # which means NULL sorts as greater than any value. This is stated
    # explicitly here and the cursor conditions follow the same rule.
    for i, (c, descending) in enumerate(columns):
        if descending != bool(last):
            ordering_arr.append(f"{c} DESC NULLS FIRST")
        else:
            ordering_arr.append(f"{c} ASC NULLS LAST")
        cursor_arr.append(f"{c} AS cursor_{i}")

    conditions = _cursor_conditions(cursor_keys)

    limit = (first or last or 500) * 2

    ordering = "ORDER BY " + ", ".join(ordering_arr) + f" LIMIT {limit}"
    cursor = ", ".join(cursor_arr)
    return ordering, conditions, cursor


class CursorKey(NamedTuple):
    key: str
    value: str | None
    nullable: bool
    operator: str


def _flip(operator: str) -> str:
    return "<" if operator == ">" else ">"


def _cursor_conditions(cursor_keys: list[CursorKey]) -> str:
    """Build the condition selecting the rows after (or before) the cursor.

    When all the sorted columns are non-nullable and sorted in the same
    direction, a row comparison `(a, b) > (x, y)` is used. Otherwise
    (comparisons with NULL are never true, and a row comparison has
    a single operator), it is expanded to `(a > x) OR (a = x AND b < y)`,
    with each column's own operator. Each comparison treats NULL
    as greater than any value (matching the ordering).
    """
    if not cursor_keys:
        return ""

    operators = {ck.operator for ck in cursor_keys}
    if len(operators) == 1 and not any(ck.nullable for ck in cursor_keys):
        # Row comparison is simpler and can use indices
        operator = operators.pop()
        keys_str = ", ".join(ck.key for ck in cursor_keys)
        vals_str = ", ".join(str(ck.value) for ck in cursor_keys)
        if len(cursor_keys) > 1:
            return f"({keys_str}) {operator} ({vals_str})"
        return f"{keys_str} {operator} {vals_str}"

    alternatives: list[str] = []
    equal: list[str] = []  # the preceding columns equal to the cursor
    for key, val, nullable, operator in cursor_keys:
        # The column is past the cursor value
        if val is None:
            # Nothing is greater than NULL, everything else is lower
            past = None if operator == ">" else f"{key} IS NOT NULL"
        elif nullable and operator == ">":
            past = f"({key} {operator} {val} OR {key} IS NULL)"
        else:
            past = f"{key} {operator} {val}"

        if past is not None:
            alternatives.append(" AND ".join([*equal, past]))

        # The column equals the cursor value
        if val is None:
            equal.append(f"{key} IS NULL")
        else:
            equal.append(f"{key} = {val}")

    if not alternatives:
        return "FALSE"
    if len(alternatives) == 1:
        return f"({alternatives[0]})"
    return "(" + " OR ".join(f"({a})" for a in alternatives) + ")"
