"""The all-settings cache against a real Redis (AYON_REDIS_URL).

Skipped when Redis is not available. The keys get a random prefix
and are deleted afterwards, so a shared Redis is safe to use.
"""

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from ayon_server.lib.redis import Redis


@pytest.fixture
def redis(run) -> Iterator[None]:
    async def connect() -> None:
        await Redis.connect()

    async def cleanup() -> None:
        for key in await Redis.redis_pool.keys(f"{Redis.prefix}*"):
            await Redis.redis_pool.delete(key)

    try:
        run(connect())
    except ConnectionError as e:
        pytest.skip(f"Redis is not available: {e}")

    original_prefix = Redis.prefix
    Redis.prefix = f"test-{uuid4().hex}-"
    try:
        yield
    finally:
        run(cleanup())
        Redis.prefix = original_prefix


def test_delete_ns_bumps_the_generation(run, redis) -> None:
    async def scenario() -> None:
        ns = "test-ns"
        assert int(await Redis.get("generation", ns) or 0) == 0

        await Redis.set(ns, "a", "1")
        await Redis.set(ns, "b", "2")
        await Redis.delete_ns(ns)

        assert await Redis.keys(ns) == []
        # what the readers do with the value (Redis returns bytes)
        assert int(await Redis.get("generation", ns) or 0) == 1

        await Redis.delete_ns(ns)
        assert int(await Redis.get("generation", ns) or 0) == 2

    run(scenario())


def test_settings_built_before_an_invalidation_are_not_served(
    run, redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    # imports ayon_server.entities, which needs the database (see conftest)
    from api.settings import settings

    loads: list[None] = []
    in_build = asyncio.Event()
    release = asyncio.Event()

    async def addon_list(**kwargs: Any) -> dict[str, Any]:
        return {"addons": {}, "bundle_name": "b", "is_project_bundle": False}

    async def load_all_settings(**kwargs: Any) -> dict[Any, Any]:
        loads.append(None)
        in_build.set()
        await release.wait()
        return {}

    monkeypatch.setattr(settings, "get_addon_list_for_settings", addon_list)
    monkeypatch.setattr(settings, "load_all_settings", load_all_settings)

    def request() -> asyncio.Task[Any]:
        return asyncio.create_task(
            settings.get_all_settings(
                user=SimpleNamespace(name="user"),  # type: ignore[arg-type]
                site_id=None,
                bundle_name=None,
                project_name=None,
                project_bundle_name=None,
                variant="production",
                summary=False,
            )
        )

    async def scenario() -> None:
        # identical requests during a build share it
        first = request()
        await asyncio.wait_for(in_build.wait(), timeout=5)
        second = request()
        await asyncio.sleep(0.05)
        # settings are saved during the build: a later request does not join it
        await Redis.delete_ns("all-settings")
        third = request()
        await asyncio.sleep(0.05)
        release.set()
        results = await asyncio.gather(first, second, third)
        assert len(loads) == 2
        assert results[0].bundle_name == "b"

        # the fresh result is served from Redis, the stale one is under
        # a key nobody reads
        cached = await request()
        assert len(loads) == 2
        assert cached.bundle_name == "b"
        assert len(await Redis.keys("all-settings")) == 2

    run(scenario())
