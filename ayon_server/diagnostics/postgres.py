from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from ayon_server.lib.postgres import Connection, Postgres

from .checks import CHECK_TIMEOUT, diagnostic_check, register_code
from .models import CodeInfo, Finding

MAX_LISTED = 20  # objects listed in a finding's params
# Small tables never reach the autoanalyze threshold and plan fine without stats
STATS_MIN_PAGES = 128  # 1 MB


@asynccontextmanager
async def readonly_connection() -> AsyncGenerator[Connection]:
    """Own read-only transaction, so a check can't join the caller's or write."""
    async with Postgres.transaction(force_new=True) as conn:
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = '{CHECK_TIMEOUT}s'")
        yield conn


register_code(
    "PG-STATS-001",
    CodeInfo(
        title="Tables without planner statistics",
        description="{count} tables have no planner statistics.",
        explanation=(
            "Without statistics the planner misestimates row counts, which "
            "leads to bad join strategies and large temp-file spills. Common "
            "right after a major version upgrade, which doesn't carry "
            "statistics over."
        ),
        remediation="Run `ANALYZE VERBOSE;` (or `vacuumdb --all --analyze-in-stages`).",
    ),
)


@diagnostic_check("postgres")
async def missing_statistics() -> list[Finding]:
    # pg_stats, not pg_stat_user_tables: activity counters can say "analyzed"
    # while the planner statistics are gone (pg_upgrade drops them).
    query = """
        SELECT n.nspname || '.' || c.relname AS name
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'm')
        AND c.relpages >= $1
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        AND n.nspname NOT LIKE 'pg\\_%'
        AND NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_stats s
            WHERE s.schemaname = n.nspname AND s.tablename = c.relname
        )
        ORDER BY c.relpages DESC
    """
    async with readonly_connection() as conn:
        rows = await conn.fetch(query, STATS_MIN_PAGES)
    if not rows:
        return []
    return [
        Finding(
            code="PG-STATS-001",
            severity="critical",
            component="postgres",
            params={
                "count": len(rows),
                "tables": [row["name"] for row in rows[:MAX_LISTED]],
            },
        )
    ]
