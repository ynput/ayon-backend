import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.graphql.resolvers.links import get_links
from ayon_server.lib.postgres import Postgres

HOSTILE = "x' OR (SELECT 1) = 1 --"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"link_types": [HOSTILE]},
        {"names": [HOSTILE]},
        {"name_ex": HOSTILE},
    ],
)
def test_quotes_in_link_filters_are_escaped(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    queries: list[str] = []

    async def iterate(query: str, *args: Any, **kw: Any):
        queries.append(query)
        return
        yield

    monkeypatch.setattr(Postgres, "iterate", iterate)
    root = SimpleNamespace(project_name="test", id="0" * 32)
    info = SimpleNamespace(context={"user": SimpleNamespace(is_manager=True)})
    args = {"direction": None, "link_types": None, **kwargs}

    asyncio.run(get_links(root, info, **args))  # type: ignore[arg-type]

    (query,) = queries
    assert HOSTILE.replace("'", "''") in query
    # the only quotes left besides the doubled ones open and close strings
    assert query.replace("''", "").count("'") % 2 == 0
