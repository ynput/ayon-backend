import os
from typing import Any

import pytest

from ayon_server.helpers.project_list import PROJECT_SCHEMAS_LOCK
from ayon_server.lib.postgres import Postgres
from setup.database import db_migration

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


async def _lock_is_free() -> bool:
    async with Postgres.acquire(force_new=True) as conn:
        key = "SELECT {}(hashtextextended($1, 0))"
        if not await conn.fetchval(
            key.format("pg_try_advisory_lock"), PROJECT_SCHEMAS_LOCK
        ):
            return False
        await conn.execute(key.format("pg_advisory_unlock"), PROJECT_SCHEMAS_LOCK)
        return True


def test_failed_migration_raises_and_releases_lock(run, monkeypatch) -> None:
    """It also runs in the server (after an import), so it must not exit"""

    async def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("broken migration")

    monkeypatch.chdir(BACKEND_DIR)  # migrations are read from a relative path
    monkeypatch.setattr(Postgres, "execute", fail)
    with pytest.raises(RuntimeError, match="broken migration"):
        run(db_migration())
    assert run(_lock_is_free())
