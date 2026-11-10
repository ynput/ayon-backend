import pytest

from ayon_server.config import ayonconfig
from ayon_server.exceptions import ServiceUnavailableException
from ayon_server.lib.postgres import Postgres

PID = "SELECT pg_backend_pid() AS pid FROM generate_series(1, 3)"


async def _value(query: str) -> int:
    row = await Postgres.fetchrow(query)
    assert row
    return row[0]


async def _iterate_in_transaction() -> None:
    async with Postgres.transaction():
        await Postgres.execute("CREATE TEMP TABLE t (i int) ON COMMIT DROP")
        await Postgres.execute("INSERT INTO t VALUES (1), (2), (3)")
        pid = await _value("SELECT pg_backend_pid()")

        seen = []
        # queries inside the loop share the connection with the open cursor
        async for row in Postgres.iterate("SELECT i FROM t ORDER BY i"):
            seen.append(row["i"])
            assert await _value("SELECT pg_backend_pid()") == pid
        assert seen == [1, 2, 3]  # sees the uncommitted rows

        async for row in Postgres.iterate(PID):
            assert row["pid"] == pid
            break  # stopping early leaves the transaction usable
        assert await _value("SELECT count(*) FROM t") == 3


async def _iterate_outside_transaction() -> None:
    assert [row["pid"] async for row in Postgres.iterate(PID)]


def test_iterate_uses_the_current_transaction(run) -> None:
    run(_iterate_in_transaction())
    run(_iterate_outside_transaction())


async def _iterate_read_timeout(monkeypatch) -> None:
    monkeypatch.setattr(ayonconfig, "postgres_read_timeout", 1)
    with pytest.raises(ServiceUnavailableException):
        async for _ in Postgres.iterate("SELECT pg_sleep(5)"):
            pass
    # a caller (e.g. a maintenance task) can lift the limit
    assert [r async for r in Postgres.iterate("SELECT pg_sleep(1.2)", timeout=0)]
    # the limit is transaction-local: the pooled connections are not affected
    assert await _value("SELECT current_setting('statement_timeout')::int") == 0


def test_iterate_stops_slow_reads(run, monkeypatch) -> None:
    run(_iterate_read_timeout(monkeypatch))
