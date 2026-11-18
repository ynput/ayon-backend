"""Page info returned by `resolve()` when rows are dropped after the query.

Paging through Postgres with dropped rows is tested in
tests/integration/test_pagination.py
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.resolvers.common import resolve
from ayon_server.graphql.resolvers.pagination import encode_cursor
from ayon_server.lib.postgres import Postgres


@dataclass
class Node:
    id: str

    @classmethod
    async def from_record(
        cls, project_name: str | None, record: dict[str, Any], context: dict[str, Any]
    ) -> "Node":
        if record["id"] in context["forbidden"]:
            raise ForbiddenException()
        return cls(record["id"])


@dataclass
class Edge:
    node: Node
    cursor: str | None


@dataclass
class Connection:
    edges: list[Edge]
    page_info: Any


def page(
    monkeypatch: pytest.MonkeyPatch,
    rows: str,
    forbidden: str = "",
    *,
    skippable: bool,
    backwards: bool = False,
) -> Connection:
    """Resolve a page of 2 from the rows the query returned."""

    async def fetch(query: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": id, "cursor_0": id} for id in rows]

    monkeypatch.setattr(Postgres, "fetch", fetch)
    return asyncio.run(
        resolve(
            Connection,
            Edge,
            Node,
            "SELECT",
            first=None if backwards else 2,
            last=2 if backwards else None,
            context={"forbidden": set(forbidden)},
            order_by=["id"],
            skippable=skippable,
        )
    )


@pytest.mark.parametrize("backwards", [False, True], ids=["first", "last"])
@pytest.mark.parametrize(
    "rows, forbidden, skippable, ids, more, end",
    [
        # The query returned fewer rows than it asked for: no more pages
        ("a", "", False, "a", False, "a"),
        ("abc", "b", True, "ac", False, "c"),
        ("abc", "abc", True, "", False, "c"),
        ("ab", "", True, "ab", False, "b"),
        # All the rows it asked for: there may be more
        ("ab", "", False, "ab", True, "b"),
        ("ab", "a", False, "b", True, "b"),
        ("ab", "ab", False, "", True, "b"),
        ("abcd", "bcd", True, "a", True, "d"),
        # Rows left unread
        ("abc", "", True, "ab", True, "b"),
    ],
)
def test_page_info(monkeypatch, backwards, rows, forbidden, skippable, ids, more, end):
    connection = page(
        monkeypatch, rows, forbidden, skippable=skippable, backwards=backwards
    )
    page_info = connection.page_info
    assert "".join(edge.node.id for edge in connection.edges) == ids
    if backwards:
        assert (page_info.has_next_page, page_info.has_previous_page) == (False, more)
    else:
        assert (page_info.has_next_page, page_info.has_previous_page) == (more, False)
    assert page_info.end_cursor == encode_cursor([end])
