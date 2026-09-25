"""Integration tests need a running Postgres database.

The connection is configured the same way as for the server
(AYON_POSTGRES_URL environment variable), for example:

    AYON_POSTGRES_URL=postgres://ayon:ayon@localhost:5432/ayon make test-integration

When the database is not available, the tests are skipped.

`ayon_server.entities` loads the attributes from the database when it is
imported, so test modules should not import it (or anything importing it)
at the module level. Use the `run` fixture instead, which imports it
after checking the database connection.
"""

import asyncio
import os
import sys
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BACKEND_DIR)

from ayon_server.lib.postgres import Postgres  # noqa: E402

Runner = Callable[[Coroutine[Any, Any, Any]], Any]


async def _connect() -> None:
    Postgres.shutting_down = False
    await Postgres.connect()


async def _disconnect() -> None:
    await Postgres.shutdown()
    Postgres.shutting_down = False


@pytest.fixture(scope="session")
def run() -> Iterator[Runner]:
    """Return a function running coroutines connected to the database."""
    if getattr(Postgres, "replaced_by_unit_tests", False):
        pytest.skip(
            "The database is replaced by the unit tests. "
            "Run the integration tests separately (make test-integration)"
        )

    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(_connect())
            loop.run_until_complete(Postgres.fetch("SELECT 1"))
        except Exception as e:
            pytest.skip(f"Database is not available: {e}")
        finally:
            loop.run_until_complete(_disconnect())

        # Loads the attributes from the database (using its own connection)
        import ayon_server.entities  # noqa: F401

        loop.run_until_complete(_connect())
        yield loop.run_until_complete
        loop.run_until_complete(_disconnect())
    finally:
        loop.close()
