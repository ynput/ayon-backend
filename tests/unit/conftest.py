"""Unit tests run without Postgres and Redis.

The database is replaced before `ayon_server` is imported:
the attribute library loads the default attributes (as deployed by
`setup`), so the entity models are complete, and any other query fails.
Tests needing the database belong to tests/integration.
"""

import os
import sys
from collections.abc import AsyncGenerator
from typing import Any

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BACKEND_DIR)

from ayon_server.lib.postgres import Postgres  # noqa: E402
from setup.attributes import default_attribute_rows  # noqa: E402

ATTRIBUTES_QUERY = "SELECT * FROM public.attributes"
NO_DATABASE = (
    "Unit tests cannot access the database. "
    "Move the test to tests/integration or mock the query."
)


async def _noop(*args: Any, **kwargs: Any) -> None:
    pass


async def _fetch(query: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    if query.strip().startswith(ATTRIBUTES_QUERY):
        return default_attribute_rows()
    raise RuntimeError(NO_DATABASE)


async def _no_database(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError(NO_DATABASE)


async def _no_database_iterate(*args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
    raise RuntimeError(NO_DATABASE)
    yield  # makes it an async generator


# Checked by tests/integration, which cannot run in the same session
Postgres.replaced_by_unit_tests = True  # type: ignore[attr-defined]
Postgres.connect = _noop  # type: ignore[method-assign]
Postgres.shutdown = _noop  # type: ignore[method-assign]
Postgres.fetch = _fetch  # type: ignore[method-assign]
Postgres.execute = _no_database  # type: ignore[method-assign]
Postgres.iterate = _no_database_iterate  # type: ignore[method-assign]

# Build the entity models with the default attributes
# (this also avoids circular imports of ayon_server.settings in tests)
import ayon_server.entities  # noqa: E402, F401
