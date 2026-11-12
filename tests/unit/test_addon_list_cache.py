import asyncio
from typing import Any

import pytest

from api.addons import list_addons
from ayon_server.lib.redis import Redis


@pytest.mark.anyio
async def test_concurrent_misses_build_once_and_variants_coexist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache: dict[tuple[str, str], Any] = {}
    builds: list[bool] = []

    async def get_json(ns: str, key: str) -> Any:
        return cache.get((ns, key))

    async def get(ns: str, key: str) -> Any:
        return cache.get((ns, key))

    async def build(base_url: str, details: bool, key: str) -> list[Any]:
        builds.append(details)
        await asyncio.sleep(0.01)
        cache[("addon-list", key)] = []
        return []

    monkeypatch.setattr(Redis, "get_json", get_json)
    monkeypatch.setattr(Redis, "get", get)
    monkeypatch.setattr(list_addons, "_build_addon_list", build)
    monkeypatch.setattr(list_addons, "_build_lock", asyncio.Lock())

    get = list_addons._get_addon_list
    await asyncio.gather(*(get("http://x", True) for _ in range(10)))
    assert builds == [True]

    await get("http://x", False)
    await get("http://x", True)
    assert builds == [True, False]

    # invalidation during a build: the stale result must not be served afterwards
    cache[("generation", "addon-list")] = 1
    task = asyncio.create_task(get("http://x", True))
    await asyncio.sleep(0)
    cache[("generation", "addon-list")] = 2
    await task
    await get("http://x", True)
    assert builds == [True, False, True, True]
