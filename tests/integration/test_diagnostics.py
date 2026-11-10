import asyncio

import pytest

from ayon_server.diagnostics import postgres as pg
from ayon_server.diagnostics.checks import CHECKS, run_checks
from ayon_server.lib.postgres import Postgres

TABLE = "public.test_diagnostics"


@pytest.fixture(autouse=True)
def _list_everything(monkeypatch) -> None:
    # Busy databases have more than MAX_LISTED objects ahead of the test ones
    monkeypatch.setattr(pg, "MAX_LISTED", 100_000)


async def _listed(check, key: str) -> list[str]:
    names = []
    for f in await check():
        names += [i if isinstance(i, str) else i["name"] for i in f.params[key]]
    return names


async def _create(rows: int) -> None:
    await Postgres.execute(f"DROP TABLE IF EXISTS {TABLE}")
    await Postgres.execute(
        f"CREATE TABLE {TABLE} WITH (autovacuum_enabled = false) AS "
        f"SELECT generate_series(1, {rows}) AS id"
    )


async def _drop() -> None:
    await Postgres.execute(f"DROP TABLE IF EXISTS {TABLE}")


async def _flush_stats(*queries: str) -> None:
    """Run queries on one connection and publish its activity counters now."""
    async with Postgres.acquire() as conn:
        for query in queries:
            await conn.execute(query)
        await conn.execute("SELECT pg_stat_force_next_flush()")
    await asyncio.sleep(0.1)


def test_all_checks_run(run) -> None:
    findings = run(run_checks(["postgres"]))
    assert not [f for f in findings if f.code == "DIAG-CHECK-FAILED"]
    assert len([c for c in CHECKS if c.component == "postgres"]) == 10


def test_missing_statistics(run) -> None:
    async def scenario() -> tuple[bool, bool]:
        await _create(100_000)
        try:
            # CREATE TABLE AS doesn't analyze; VACUUM sets relpages without stats
            await Postgres.execute(f"VACUUM {TABLE}")
            before = TABLE in await _listed(pg.missing_statistics, "tables")
            await Postgres.execute(f"ANALYZE {TABLE}")
            after = TABLE in await _listed(pg.missing_statistics, "tables")
        finally:
            await _drop()
        return before, after

    assert run(scenario()) == (True, False)


def test_stale_statistics_and_dead_tuples(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "STALE_STATS_MIN_ROWS", 10)
    monkeypatch.setattr(pg, "DEAD_TUPLES_MIN", 100)

    async def scenario() -> tuple[bool, bool]:
        await _create(1000)
        try:
            # 900 modified and dead rows, 100 live ones
            await _flush_stats(
                f"ANALYZE {TABLE}", f"DELETE FROM {TABLE} WHERE id > 100"
            )
            stale = TABLE in await _listed(pg.stale_statistics, "tables")
            dead = TABLE in await _listed(pg.dead_tuples, "tables")
        finally:
            await _drop()
        return stale, dead

    assert run(scenario()) == (True, True)


def test_invalid_index(run) -> None:
    async def scenario() -> bool:
        await _create(10)
        await Postgres.execute(f"INSERT INTO {TABLE} VALUES (1)")
        try:
            # fails on the duplicate and leaves the index behind, invalid
            with pytest.raises(Exception):
                await Postgres.execute(
                    f"CREATE UNIQUE INDEX CONCURRENTLY test_diagnostics_invalid "
                    f"ON {TABLE} (id)"
                )
            names = await _listed(pg.invalid_indexes, "indexes")
            return "public.test_diagnostics_invalid" in names
        finally:
            await _drop()

    assert run(scenario())


def test_sequential_scans_and_unused_index(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "SEQ_SCAN_MIN_PAGES", 0)
    monkeypatch.setattr(pg, "SEQ_SCAN_MIN_COUNT", 3)
    monkeypatch.setattr(pg, "UNUSED_INDEX_MIN_PAGES", 0)

    async def scenario() -> tuple[bool, bool]:
        await _create(1000)
        try:
            await Postgres.execute(
                f"CREATE INDEX test_diagnostics_unused ON {TABLE} (id)"
            )
            await _flush_stats(*[f"SELECT count(*) FROM {TABLE}"] * 3)
            seq = TABLE in await _listed(pg.sequential_scans, "tables")
            unused = "public.test_diagnostics_unused" in await _listed(
                pg.unused_indexes, "indexes"
            )
        finally:
            await _drop()
        return seq, unused

    assert run(scenario()) == (True, True)


def test_long_running(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "LONG_RUNNING_SECONDS", 0)

    async def scenario() -> bool:
        async with Postgres.transaction(force_new=True) as conn:
            await conn.execute("SELECT 1")  # now idle in transaction
            pid = await conn.fetchval("SELECT pg_backend_pid()")
            await asyncio.sleep(1.1)
            findings = await pg.long_running()
        return any(s["pid"] == pid for f in findings for s in f.params["sessions"])

    assert run(scenario())


def test_xid_wraparound_severity(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "XID_AGE_WARNING", 0)
    assert run(pg.xid_wraparound())[0].severity == "warning"
    monkeypatch.setattr(pg, "XID_AGE_CRITICAL", 0)
    assert run(pg.xid_wraparound())[0].severity == "critical"


def test_cache_hit_ratio(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "CACHE_MIN_BLOCKS", 0)
    assert run(pg.cache_hit_ratio()) == []
    monkeypatch.setattr(pg, "CACHE_HIT_MIN_RATIO", 1.01)
    assert run(pg.cache_hit_ratio())[0].code == "PG-CACHE-001"


def test_default_settings(run, monkeypatch) -> None:
    monkeypatch.setattr(pg, "TUNED_SETTINGS", ["work_mem", "no_such_setting"])
    names = run(_listed(pg.default_settings, "settings"))

    async def boot() -> bool:
        row = await Postgres.fetchrow(
            "SELECT setting = boot_val AS d FROM pg_settings WHERE name = 'work_mem'"
        )
        return row["d"]

    assert names == (["work_mem"] if run(boot()) else [])
