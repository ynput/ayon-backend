import re
from base64 import b64decode, b64encode
from typing import Any

from ayon_server.logging import logger
from ayon_server.utils import json_dumps, json_loads


def decode_cursor(cursor: str | None) -> tuple[list[str], list[str]]:
    """
    returns a list of cursor values and casts
    """

    if not cursor:
        return ([], [])
    try:
        cur_data = json_loads(b64decode(cursor).decode())
        vals = []
        casts = []
        for c in cur_data:
            if isinstance(c, str):
                # Check if the value is a timestamp in ISO format
                if re.match(r"^\d{4}-\d{2}-\d{2}T[0-9:\.\+\-Z]+$", c):
                    # Convert to timestamp
                    vals.append(f"'{c}'::timestamptz")
                    casts.append("::timestamptz")
                else:
                    val = c.replace("'", "''") if c else ""
                    vals.append(f"'{val}'::text")
                    casts.append("::text")
            else:
                vals.append(f"{c or 0}::numeric")
                casts.append("::numeric")
        return vals, casts
    except Exception as e:
        logger.debug(f"Invalid cursor {e}")
        return ([], [])


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
    decoded_cursor, casts = decode_cursor(before or after)
    operator = "<" if before else ">"

    keys = []
    for i in range(min(len(order_by), len(decoded_cursor))):
        ob = order_by[i]
        cast = casts[i]
        if "->" in ob:
            if cast == "::numeric":
                keys.append(f"COALESCE({ob}, '0'::jsonb){cast}")
            elif cast == "::timestamptz":
                keys.append(f"COALESCE({ob}, '1970-01-01T00:00:00Z'::jsonb){cast}")
            else:
                keys.append(f"COALESCE({ob}, ''::jsonb){cast}")
        else:
            if cast == "::numeric":
                keys.append(f"COALESCE({ob}, 0){cast}")
            elif cast == "::timestamptz":
                keys.append(f"COALESCE({ob}, '1970-01-01T00:00:00Z'){cast}")
            else:
                keys.append(f"COALESCE({ob}, ''){cast}")

    for i, c in enumerate(order_by):
        cursor_arr.append(f"{c} AS cursor_{i}")
        ordering_arr.append(f"{c} {'DESC NULLS LAST' if last else 'ASC NULLS FIRST'}")

    if not keys:
        conditions = ""
    else:
        cond_parts = []
        for i in range(len(keys)):
            line = []
            for j in range(i):
                line.append(f"{keys[j]} = {decoded_cursor[j]}")
            line.append(f"{keys[i]} {operator} {decoded_cursor[i]}")
            cond_parts.append(f"({' AND '.join(line)})")

        conditions = f"({' OR '.join(cond_parts)})"

    ordering = "ORDER BY " + ", ".join(ordering_arr)
    cursor = ", ".join(cursor_arr)
    return ordering, conditions, cursor
