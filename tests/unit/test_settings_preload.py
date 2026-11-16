from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.addons.addon import BaseServerAddon
from ayon_server.addons.settings_caching import load_all_settings
from ayon_server.lib.postgres import Postgres


@pytest.mark.anyio
async def test_addons_do_not_query_again_after_the_preload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = {"key": "value"}

    async def iterate(query: str, *args: Any) -> AsyncGenerator[dict[str, Any]]:
        # only addon "a" has a row, and only on the studio level
        if "public.settings" in query:
            yield {"addon_name": "a", "addon_version": "1", "data": saved}

    async def no_query(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("The addon queried the database after the preload")

    monkeypatch.setattr(Postgres, "iterate", iterate)
    monkeypatch.setattr(Postgres, "fetch", no_query)
    monkeypatch.setattr(Postgres, "fetchrow", no_query)

    cache = await load_all_settings(
        {"a": "1", "b": "2"}, project_name="p", user_name="u", site_id="s"
    )
    assert cache["a", "1"].studio == saved

    addon: Any = SimpleNamespace(
        name="x",
        version="1",
        definition=SimpleNamespace(name="x"),
        get_site_settings_model=lambda: dict,
    )
    for key in (("a", "1"), ("b", "2")):
        c = cache[key]
        expected = saved if key == ("a", "1") else {}
        assert (
            await BaseServerAddon.get_studio_overrides(addon, settings_cache=c)
            == expected
        )
        assert (
            await BaseServerAddon.get_project_overrides(addon, "p", settings_cache=c)
            == {}
        )
        assert (
            await BaseServerAddon.get_project_site_overrides(
                addon, "p", "u", "s", settings_cache=c
            )
            == {}
        )
        # no saved site settings is None, not the model defaults
        assert (
            await BaseServerAddon.get_site_settings(addon, "u", "s", settings_cache=c)
            is None
        )
