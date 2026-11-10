from ayon_server.diagnostics.postgres import missing_statistics
from ayon_server.lib.postgres import Postgres

TABLE = "public.test_diagnostics_no_stats"


async def _flagged() -> bool:
    findings = await missing_statistics()
    return any(TABLE in f.params["tables"] for f in findings)


async def _scenario() -> tuple[bool, bool]:
    await Postgres.execute(f"DROP TABLE IF EXISTS {TABLE}")
    await Postgres.execute(
        f"CREATE TABLE {TABLE} AS SELECT generate_series(1, 100000) AS id"
    )
    try:
        # CREATE TABLE AS doesn't analyze; VACUUM sets relpages without stats
        await Postgres.execute(f"VACUUM {TABLE}")
        before = await _flagged()
        await Postgres.execute(f"ANALYZE {TABLE}")
        after = await _flagged()
    finally:
        await Postgres.execute(f"DROP TABLE IF EXISTS {TABLE}")
    return before, after


def test_missing_statistics(run) -> None:
    assert run(_scenario()) == (True, False)
