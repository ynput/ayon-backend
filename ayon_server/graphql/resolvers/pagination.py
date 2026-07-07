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

    keys = []
    cursor_values = []
    for i in range(min(len(order_by), len(decoded_cursor))):
        ob = order_by[i]
        val = decoded_cursor[i]
        col_name = ob.split(".")[-1]

        is_jsonb = ("->" in ob) and ("->>" not in ob) and ("::" not in ob)
        ctype = COLUMN_TYPES.get(col_name)

        if ctype and not is_jsonb:
            # Known non-nullable top-level field
            keys.append(f"{ob}")
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
            cursor_values.append(sql_val)
            continue

        # Fallback for nullable fields or JSONB
        if isinstance(val, (int, float)):
            cast = "numeric"
            # default = "'0'"
            sql_val = f"{val}::numeric"
        elif isinstance(val, str) and re.match(
            r"^\d{4}-\d{2}-\d{2}T[0-9:\.\+\-Z]+$", val
        ):
            cast = "timestamptz"
            # default = "'1970-01-01T00:00:00Z'"
            sql_val = f"'{val}'::timestamptz"
        else:
            cast = "text"
            # default = "'\"\"'"
            v_str = str(val).replace("'", "''") if val is not None else ""
            sql_val = f"'{v_str}'::text"

        # if is_jsonb:
        #     keys.append(f"COALESCE({ob}, {default}::jsonb)::{cast}")
        # else:
        #     keys.append(f"COALESCE({ob}, {default})::{cast}")

        keys.append(f"({ob})::{cast}")
        cursor_values.append(sql_val)

    for i, c in enumerate(order_by):
        ordering_arr.append(f"{c} {'DESC' if last else 'ASC'}")
        cursor_arr.append(f"{c} AS cursor_{i}")

    #
    # Create cursor conditions
    #

    if not keys:
        conditions = ""
    else:
        if len(keys) > 1:
            keys_str = ", ".join(keys)
            vals_str = ", ".join(cursor_values)
            conditions = f"({keys_str}) {operator} ({vals_str})"
        else:
            conditions = f"{keys[0]} {operator} {cursor_values[0]}"

    limit = (first or last or 500) * 2

    ordering = "ORDER BY " + ", ".join(ordering_arr) + f" LIMIT {limit}"
    cursor = ", ".join(cursor_arr)
    return ordering, conditions, cursor
