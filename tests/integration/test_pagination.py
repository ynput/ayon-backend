"""Paging through rows with NULL sort values returns every row exactly once."""

from typing import Any

import pytest

# id, label, num, data
ROWS = [
    ("01", "b", 2, '{"fps": "25"}'),
    ("02", None, 1, '{"fps": "25"}'),
    ("03", "a", None, "{}"),
    ("04", None, None, '{"fps": null}'),
    ("05", "b", 1, '{"fps": "24"}'),
    ("06", "it's", None, '{"fps": "30"}'),
    ("07", None, 2, "{}"),
    ("08", "a", 2, '{"fps": "25"}'),
    ("09", "b", None, '{"fps": "24"}'),
    ("10", None, 1, "{}"),
    ("11", "c", 3, '{"fps": "30"}'),
]

SORTINGS = [
    ["t.label", "t.id"],
    ["t.num", "t.id"],
    ["(t.data->>'fps')", "t.id"],
    ["t.label", "t.num", "t.id"],
    ["t.num", "t.label", "t.id"],
]


def _query(order_by: list[str], **kwargs: Any) -> str:
    from ayon_server.graphql.resolvers.pagination import create_pagination

    ordering, conditions, cursor = create_pagination(order_by, **kwargs)
    values = ", ".join(
        "('{}', {}, {}, '{}'::jsonb)".format(
            id,
            "NULL" if label is None else "'{}'".format(label.replace("'", "''")),
            "NULL" if num is None else num,
            data,
        )
        for id, label, num, data in ROWS
    )
    return f"""
        WITH t(id, label, num, data) AS (VALUES {values})
        SELECT t.id, {cursor} FROM t
        {"WHERE " + conditions if conditions else ""}
        {ordering}
    """


async def _walk(order_by: list[str], page_size: int, backwards: bool) -> list[str]:
    from ayon_server.graphql.resolvers.pagination import encode_cursor
    from ayon_server.lib.postgres import Postgres

    result: list[str] = []
    cursor: str | None = None
    for _ in range(len(ROWS) + 1):
        if backwards:
            query = _query(order_by, last=page_size, before=cursor)
        else:
            query = _query(order_by, first=page_size, after=cursor)
        page = (await Postgres.fetch(query))[:page_size]
        if not page:
            return result
        result.extend(row["id"] for row in page)
        last_row = page[-1]
        cursor = encode_cursor([last_row[f"cursor_{i}"] for i in range(len(order_by))])
    raise AssertionError("Paging did not finish")


async def _all(order_by: list[str], backwards: bool) -> list[str]:
    from ayon_server.lib.postgres import Postgres

    kwargs = {"last": len(ROWS)} if backwards else {"first": len(ROWS)}
    return [row["id"] for row in await Postgres.fetch(_query(order_by, **kwargs))]


@pytest.mark.parametrize("order_by", SORTINGS, ids=lambda s: ",".join(s))
@pytest.mark.parametrize("backwards", [False, True], ids=["forward", "backward"])
@pytest.mark.parametrize("page_size", [1, 2, 3])
def test_paging_returns_every_row_once(run, order_by, backwards, page_size):
    expected = run(_all(order_by, backwards))
    assert sorted(expected) == sorted(row[0] for row in ROWS)
    assert run(_walk(order_by, page_size, backwards)) == expected
