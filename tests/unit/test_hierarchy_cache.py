"""The folder list cache with a fake Redis and a mocked folder query.

A rebuild reads all folders, which takes a while on big projects. When the
cache is invalidated meanwhile, the rebuild may have read the old data, so
it must not stay cached.
"""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from ayon_server.helpers.hierarchy_cache import (
    invalidate_hierarchy_cache,
    rebuild_hierarchy_cache,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import json_dumps, json_loads

PROJECT = "testproject"


def _row(folder_id: str, parent_id: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": folder_id,
        "path": f"/{folder_id}" if parent_id is None else f"/{parent_id}/{folder_id}",
        "parent_id": parent_id,
        "name": folder_id,
        "label": None,
        "folder_type": "Shot",
        "task_count": 0,
        "task_names": [],
        "status": "Not ready",
        "all_attrib": {"fps": 25},
        "attrib": {},
        "tags": [],
        "has_reviewables": False,
        "has_versions": False,
        "thumbnail_hash": None,
        "active": True,
        "visible": True,
        "created_at": now,
        "updated_at": now,
        "created_by": None,
        "updated_by": None,
    }


@pytest.fixture
def redis(monkeypatch) -> dict[str, Any]:
    """Replace Redis with a dict (keyed by namespace-key, like Redis)."""
    store: dict[str, Any] = {}

    async def get(namespace: str, key: str) -> Any:
        return store.get(f"{namespace}-{key}")

    async def set(namespace: str, key: str, value: Any, ttl: int = 0) -> None:
        store[f"{namespace}-{key}"] = value

    async def delete(namespace: str, key: str) -> None:
        store.pop(f"{namespace}-{key}", None)

    async def incr(namespace: str, key: str, *, ttl: int = 0) -> int:
        store[f"{namespace}-{key}"] = store.get(f"{namespace}-{key}", 0) + 1
        return store[f"{namespace}-{key}"]

    for name, func in {"get": get, "set": set, "delete": delete, "incr": incr}.items():
        monkeypatch.setattr(Redis, name, func)
    return store


@pytest.fixture
def folders(monkeypatch) -> Callable[..., None]:
    """Set the rows the folder query returns, and what runs while reading."""
    state: dict[str, Any] = {"rows": [], "while_reading": None}

    class Statement:
        async def cursor(self):
            for i, row in enumerate(state["rows"]):
                if i == 1 and state["while_reading"]:
                    await state["while_reading"]()
                yield row

    async def prepare(query: str) -> Statement:
        return Statement()

    @asynccontextmanager
    async def transaction():
        yield

    async def set_project_schema(project_name: str) -> None:
        pass

    monkeypatch.setattr(Postgres, "prepare", prepare)
    monkeypatch.setattr(Postgres, "transaction", transaction)
    monkeypatch.setattr(Postgres, "set_project_schema", set_project_schema)

    def setup(rows: list[dict[str, Any]], while_reading=None) -> None:
        state["rows"] = rows
        state["while_reading"] = while_reading

    return setup


async def concurrent_write() -> None:
    await invalidate_hierarchy_cache(PROJECT)


def cached(redis: dict[str, Any]) -> Any:
    value = redis.get(f"project-folders-{PROJECT}")
    return None if value is None else json_loads(value)


def test_rebuild_caches_the_list(redis, folders):
    folders([_row("a"), _row("b", "a")])
    result = asyncio.run(rebuild_hierarchy_cache(PROJECT))

    assert cached(redis) == json_loads(json_dumps(result))
    by_id = {f["id"]: f for f in result}
    assert by_id["a"]["has_children"]
    assert not by_id["b"]["has_children"]
    assert by_id["b"]["parents"] == ["a"]
    assert by_id["a"]["task_names"] == []


def test_invalidate_drops_the_list(redis, folders):
    folders([_row("a")])
    asyncio.run(rebuild_hierarchy_cache(PROJECT))
    asyncio.run(invalidate_hierarchy_cache(PROJECT))
    assert cached(redis) is None


def test_invalidate_during_rebuild_discards_it(redis, folders):
    folders([_row("a"), _row("b")], while_reading=concurrent_write)
    result = asyncio.run(rebuild_hierarchy_cache(PROJECT))

    # the caller still gets its result, it is just not cached
    assert [f["id"] for f in result] == ["a", "b"]
    assert cached(redis) is None


def test_invalidate_before_rebuild_keeps_it(redis, folders):
    folders([_row("a")])
    asyncio.run(invalidate_hierarchy_cache(PROJECT))
    asyncio.run(rebuild_hierarchy_cache(PROJECT))
    assert cached(redis) is not None


def test_rebuild_after_discarded_one_is_cached(redis, folders):
    folders([_row("a"), _row("b")], while_reading=concurrent_write)
    asyncio.run(rebuild_hierarchy_cache(PROJECT))
    folders([_row("a"), _row("b")])
    asyncio.run(rebuild_hierarchy_cache(PROJECT))
    assert cached(redis) is not None


def test_expired_generation_counter(redis, folders):
    """The counter has a TTL; a rebuild without it still caches."""
    folders([_row("a")])
    asyncio.run(invalidate_hierarchy_cache(PROJECT))
    redis.pop(f"project-folders-gen-{PROJECT}")
    asyncio.run(rebuild_hierarchy_cache(PROJECT))
    assert cached(redis) is not None
