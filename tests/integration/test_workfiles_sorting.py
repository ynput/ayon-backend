"""Sorting workfiles by the file name part of their path in Postgres.

The sort keys and the generated SQL are tested in
tests/unit/test_workfiles_sorting.py
"""

import re
from typing import Any

import pytest

from ayon_server.lib.postgres import Postgres

# The file names look like timestamps, contain quotes
# and are shared by several paths
PATHS = [
    "/shots/sh010/work/2024-01-01T10.30",
    "/shots/sh010/work/2024-01-01T10",
    "/shots/sh020/work/2024-01-01T10.30",
    "C:\\projects\\sh010\\work\\scene_v001.ma",
    "C:\\projects\\sh010/work/scene_v002.ma",
    "/shots/sh010/work/scene_v001.ma",
    "/shots/sh010/work/it's.ma",
    "/shots/sh010/work/1001",
    "no_folder.ma",
    "/shots/sh030/work/",
]


def _name(path: str) -> str:
    return re.split(r"[/\\]", path)[-1]


async def _query(sort_by: str, **kwargs: Any) -> str:
    # imports ayon_server.entities (see conftest)
    from ayon_server.graphql.resolvers.pagination import create_pagination
    from ayon_server.graphql.resolvers.workfiles import get_workfiles_order_by

    order_by = await get_workfiles_order_by(sort_by)
    ordering, conditions, cursor = create_pagination(order_by, **kwargs)
    values = ", ".join(
        "('{}', {})".format(path.replace("'", "''"), i) for i, path in enumerate(PATHS)
    )
    return f"""
        WITH workfiles(path, creation_order) AS (VALUES {values})
        SELECT workfiles.path, {cursor} FROM workfiles
        {"WHERE " + conditions if conditions else ""}
        {ordering}
    """


async def _walk(sort_by: str, page_size: int, backwards: bool) -> list[str]:
    from ayon_server.graphql.resolvers.pagination import encode_cursor

    result: list[str] = []
    cursor: str | None = None
    for _ in range(len(PATHS) + 1):
        if backwards:
            query = await _query(sort_by, last=page_size, before=cursor)
        else:
            query = await _query(sort_by, first=page_size, after=cursor)
        page = (await Postgres.fetch(query))[:page_size]
        if not page:
            return result
        result.extend(row["path"] for row in page)
        last_row = page[-1]
        cursor = encode_cursor([last_row["cursor_0"], last_row["cursor_1"]])
    raise AssertionError("Paging did not finish")


async def _all(sort_by: str, backwards: bool) -> list[dict[str, Any]]:
    kwargs = {"last": len(PATHS)} if backwards else {"first": len(PATHS)}
    return await Postgres.fetch(await _query(sort_by, **kwargs))


def test_name_is_the_last_segment_of_the_path(run):
    rows = run(_all("name", backwards=False))
    assert {row["path"]: row["cursor_0"] for row in rows} == {
        path: _name(path) for path in PATHS
    }


@pytest.mark.parametrize("sort_by", ["name", "-name", "path"])
@pytest.mark.parametrize("backwards", [False, True], ids=["forward", "backward"])
@pytest.mark.parametrize("page_size", [1, 2, 3])
def test_paging_returns_every_row_once(run, sort_by, backwards, page_size):
    expected = [row["path"] for row in run(_all(sort_by, backwards))]
    assert sorted(expected) == sorted(PATHS)
    assert run(_walk(sort_by, page_size, backwards)) == expected
