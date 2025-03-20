from base64 import b64decode, b64encode
from typing import Any

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException
from ayon_server.logging import logger
from ayon_server.utils import json_dumps, json_loads


async def get_attrib_sort_case(attr: str, exp: str) -> str:
    try:
        attr_data = attribute_library.by_name(attr)
    except KeyError:
        raise BadRequestException(f"Invalid attribute {attr}")
    enum = attr_data.get("enum", [])
    if not enum:
        return f"{exp}->'{attr}'"
    case = "CASE"
    i = 0
    for i, eval in enumerate(enum):
        e = eval["value"]
        case += f" WHEN {exp}->>'{attr}' = '{e}' THEN {i}"
    case += f" ELSE {i+1}"
    case += " END"
    return case


def decode_cursor(cursor: str | None) -> list[Any]:
    if not cursor:
        return []
    try:
        return json_loads(b64decode(cursor).decode())
    except Exception as e:
        logger.debug(f"Invalid cursor {e}")
        return []


def encode_cursor(decoded_cursor: list[Any]) -> str:
    return b64encode(json_dumps(decoded_cursor).encode()).decode()


def get_casts(decoded_cursor: list[Any]) -> list[str]:
    casts = []
    for dval in decoded_cursor:
        if isinstance(dval, str):
            casts.append("::text")
        else:
            casts.append("::numeric")
    return casts


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

    if len(order_by) > 2:
        raise ValueError("Order by can have only two fields")

    cursor_arr = []
    ordering_arr = []
    decoded_cursor = decode_cursor(before or after)
    casts = get_casts(decoded_cursor)
    operator = "<" if before else ">"

    for i, c in enumerate(order_by):
        cursor_arr.append(f"{c} AS cursor_{i}")
        ordering_arr.append(f"{c} {'DESC' if last else ''}")

    # Okay. I know this looks like something a 5YO would write, but hear me out.
    # We don't need to support more than two cursors. Hopefully.
    # So trust me, even if this is a mess, it is still MUCH more readable than
    # doing it a loop for every cursor element. We just cover two cases,
    # (or three if you're counting 'no cursor').

    if len(decoded_cursor) == 1:
        conditions = f"""
        ({order_by[0]}){casts[0]} {operator} {decoded_cursor[0]}{casts[0]}
        """
    elif len(decoded_cursor) == 2:
        conditions = f"""
(
    ({order_by[0]}){casts[0]} {operator} {decoded_cursor[0]}{casts[0]}
    OR (
        ({order_by[0]}){casts[0]} = {decoded_cursor[0]}{casts[0]}
        AND
        ({order_by[1]}){casts[1]} {operator} {decoded_cursor[1]}{casts[1]}
    )
)
"""
    else:
        conditions = ""

    ordering = "ORDER BY " + ", ".join(ordering_arr)
    cursor = ", ".join(cursor_arr)
    return ordering, conditions, cursor
