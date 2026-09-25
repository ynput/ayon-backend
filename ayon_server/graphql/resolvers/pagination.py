import re
from base64 import b64decode, b64encode
from typing import Any

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


def with_tiebreakers(order_by: list[str], *columns: str) -> list[str]:
    """Append the columns which are not already sorted by.

    Keyset pagination needs a unique ordering, otherwise rows sharing
    the same sort values may be skipped or repeated between pages.
    """
    return order_by + [c for c in columns if c not in order_by]


def create_pagination(
    order_by: list[str],
    first: int | None = None,
    after: str | None = None,
    last: int | None = None,
    before: str | None = None,
) -> tuple[str, str, str]:
    """
    Generates a pagination SQL query for a GraphQL resolver.

    Accepts a list of columns to sort by and GraphQL pagination
    parameters (`after`, `before`, `first`, `last`).

    Returns a tuple of three strings: `ordering`, `conditions`, and `cursor`.

    - `ordering`: The "ORDER BY" clause of the query,
        including the `ORDER BY` statement itself.
    - `conditions`: Conditions for the `WHERE` clause,
        meant to be combined with other conditions using `AND`.
    - `cursor`: A set of virtual columns in the `SELECT` section,
        which the resolver uses to construct the actual cursor.
    """

    cursor_arr = []
    ordering_arr = []
    decoded_cursor = decode_cursor(before or after)
    operator = "<" if before else ">"

    # One (key, value, nullable) item per sorted column the cursor covers.
    # `key` is the expression compared with `value` (a SQL literal,
    # or None when the cursor value is NULL) and `nullable` tells
    # whether the expression may evaluate to NULL.
    cursor_keys: list[tuple[str, str | None, bool]] = []
    for i in range(min(len(order_by), len(decoded_cursor))):
        ob = order_by[i]
        val = decoded_cursor[i]
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
            cursor_keys.append((f"{ob}", sql_val, False))
            continue

        # Nullable fields or JSONB
        if val is None:
            # The type does not matter, NULL is only tested with IS [NOT] NULL
            cursor_keys.append((f"({ob})", None, True))
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

        cursor_keys.append((f"({ob})::{cast}", sql_val, True))

    # Postgres puts NULLs last in ascending and first in descending order,
    # which means NULL sorts as greater than any value. This is stated
    # explicitly here and the cursor conditions follow the same rule.
    for i, c in enumerate(order_by):
        if last:
            ordering_arr.append(f"{c} DESC NULLS FIRST")
        else:
            ordering_arr.append(f"{c} ASC NULLS LAST")
        cursor_arr.append(f"{c} AS cursor_{i}")

    conditions = _cursor_conditions(cursor_keys, operator)

    limit = (first or last or 500) * 2

    ordering = "ORDER BY " + ", ".join(ordering_arr) + f" LIMIT {limit}"
    cursor = ", ".join(cursor_arr)
    return ordering, conditions, cursor


def _cursor_conditions(
    cursor_keys: list[tuple[str, str | None, bool]],
    operator: str,
) -> str:
    """Build the condition selecting the rows after (or before) the cursor.

    Comparisons with NULL are never true, so when any of the sorted columns
    is nullable, the row comparison `(a, b) > (x, y)` is expanded to
    `(a > x) OR (a = x AND b > y)`, where each comparison treats NULL
    as greater than any value (matching the ordering).
    """
    if not cursor_keys:
        return ""

    if not any(nullable for _, _, nullable in cursor_keys):
        # Row comparison is simpler and can use indices
        keys_str = ", ".join(key for key, _, _ in cursor_keys)
        vals_str = ", ".join(str(val) for _, val, _ in cursor_keys)
        if len(cursor_keys) > 1:
            return f"({keys_str}) {operator} ({vals_str})"
        return f"{keys_str} {operator} {vals_str}"

    alternatives: list[str] = []
    equal: list[str] = []  # the preceding columns equal to the cursor
    for key, val, nullable in cursor_keys:
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
