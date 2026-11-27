"""Entity lists are filtered by the access condition in the query."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.entities import ProjectEntity
from ayon_server.graphql.resolvers.entity_lists import get_entity_lists
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.lib.postgres import Postgres


def list_queries(monkeypatch: pytest.MonkeyPatch, condition: str | None) -> str:
    queries: list[str] = []

    async def fetch(query: str, *args: Any, **kwargs: Any) -> list[Any]:
        queries.append(query)
        return []

    async def load(project_name: str) -> Any:
        return SimpleNamespace(name=project_name)

    async def sql_condition(user: Any, **kwargs: Any) -> str | None:
        assert kwargs["level"] == EntityAccessHelper.READ
        return condition

    monkeypatch.setattr(Postgres, "fetch", fetch)
    monkeypatch.setattr(ProjectEntity, "load", load)
    monkeypatch.setattr(EntityAccessHelper, "sql_condition", sql_condition)

    root = SimpleNamespace(project_name="test")
    info: Any = SimpleNamespace(context={"user": SimpleNamespace(is_guest=False)})
    asyncio.run(get_entity_lists(root, info, first=10))
    assert len(queries) == 1
    return queries[0]


def test_access_condition_in_query(monkeypatch):
    query = list_queries(monkeypatch, "owner = 'artist'")
    assert "owner = 'artist'" in query.split("WHERE", 1)[1]


def test_no_access_condition(monkeypatch):
    query = list_queries(monkeypatch, None)
    assert "owner" not in query
