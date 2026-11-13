import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from api.settings import settings
from ayon_server.lib.redis import Redis


@pytest.mark.anyio
async def test_identical_requests_share_a_build_and_stale_builds_are_not_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache: dict[tuple[str, str], Any] = {}
    loads: list[None] = []
    in_build = asyncio.Event()
    release = asyncio.Event()

    async def get(ns: str, key: str) -> Any:
        return cache.get((ns, key))

    async def redis_set(ns: str, key: str, value: str, ttl: int = 0) -> None:
        # called at the end of a build, while it holds the semaphore
        in_build.set()
        await release.wait()
        cache[(ns, key)] = {"bundleName": "b", "addons": []}

    async def addon_list(**kwargs: Any) -> dict[str, Any]:
        return {"addons": {}, "bundle_name": "b", "is_project_bundle": False}

    async def load_all_settings(**kwargs: Any) -> dict[Any, Any]:
        loads.append(None)
        return {}

    monkeypatch.setattr(Redis, "get", get)
    monkeypatch.setattr(Redis, "get_json", get)
    monkeypatch.setattr(Redis, "set", redis_set)
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

    # the second request arrives while the first build holds the semaphore
    first = request()
    await asyncio.wait_for(in_build.wait(), timeout=1)
    second = request()
    await asyncio.sleep(0.01)
    # invalidation during the build: a later request does not join it
    cache[("generation", "all-settings")] = 1
    third = request()
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, second, third)
    assert len(loads) == 2

    # the fresh result is cached, the stale one is not served
    await request()
    assert len(loads) == 2
