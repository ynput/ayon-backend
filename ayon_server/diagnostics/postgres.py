from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from ayon_server.lib.postgres import Connection, Postgres

from .checks import CHECK_TIMEOUT, diagnostic_check, register_code
from .models import CodeInfo, Finding, Severity

MAX_LISTED = 20  # objects listed in a finding's params

# Thresholds are module globals so tests can lower them.
# Small tables never reach the autoanalyze threshold and plan fine without stats
STATS_MIN_PAGES = 128  # 1 MB
STALE_STATS_MIN_ROWS = 10_000
STALE_STATS_RATIO = 0.5  # autoanalyze runs at 0.1, so autovacuum is behind
DEAD_TUPLES_MIN = 10_000
DEAD_TUPLES_RATIO = 0.5  # autovacuum runs at 0.2
XID_AGE_WARNING = 500_000_000
XID_AGE_CRITICAL = 1_000_000_000  # wraparound shutdown at ~2.1 billion
SEQ_SCAN_MIN_PAGES = 12_800  # 100 MB
SEQ_SCAN_MIN_COUNT = 1000
UNUSED_INDEX_MIN_PAGES = 1280  # 10 MB
LONG_RUNNING_SECONDS = 300
CACHE_HIT_MIN_RATIO = 0.9
CACHE_MIN_BLOCKS = 1_000_000
# Defaults sized for a tiny machine. Others (hash_mem_multiplier) are fine as is
TUNED_SETTINGS = [
    "shared_buffers",
    "work_mem",
    "maintenance_work_mem",
    "effective_cache_size",
    "random_page_cost",
]

STATS_SINCE = (
    " Counters cover the time since the statistics were last reset, "
    "so a recent restart or upgrade makes this less reliable."
)


@asynccontextmanager
async def readonly_connection() -> AsyncGenerator[Connection]:
    """Own read-only transaction, so a check can't join the caller's or write."""
    async with Postgres.transaction(force_new=True) as conn:
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = '{CHECK_TIMEOUT}s'")
        yield conn


async def fetch(query: str, *args: Any) -> list[dict[str, Any]]:
    async with readonly_connection() as conn:
        return [dict(row) for row in await conn.fetch(query, *args)]


def listing(code: str, severity: Severity, key: str, items: list[Any]) -> list[Finding]:
    """One finding with the count and the first items, or none."""
    if not items:
        return []
    params = {"count": len(items), key: items[:MAX_LISTED]}
    return [Finding(code=code, severity=severity, component="postgres", params=params)]


#
# Statistics
#

register_code(
    "PG-STATS-001",
    CodeInfo(
        title="Tables without planner statistics",
        description="{count} tables have no planner statistics.",
        explanation=(
            "Without statistics the planner misestimates row counts, which "
            "leads to bad join strategies and large temp-file spills. Common "
            "right after a major version upgrade or a restore from a dump, "
            "which don't carry statistics over."
        ),
        remediation="Run `ANALYZE VERBOSE;` (or `vacuumdb --all --analyze-in-stages`).",
    ),
)


@diagnostic_check("postgres")
async def missing_statistics() -> list[Finding]:
    # pg_stats, not pg_stat_user_tables: activity counters can say "analyzed"
    # while the planner statistics are gone (pg_upgrade drops them).
    rows = await fetch(
        """
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
        """,
        STATS_MIN_PAGES,
    )
    return listing("PG-STATS-001", "critical", "tables", [r["name"] for r in rows])


register_code(
    "PG-STATS-002",
    CodeInfo(
        title="Stale planner statistics",
        description=(
            "{count} tables changed substantially since they were last analyzed."
        ),
        explanation=(
            "Most rows of these tables were modified since the last ANALYZE, "
            "so the planner works with outdated row counts. Autovacuum should "
            "have analyzed them long ago: it may be disabled for the tables, "
            "or too busy to keep up."
        ),
        remediation=(
            "Run `ANALYZE <table>;` for the listed tables and check that "
            "autovacuum is enabled and has enough workers."
        ),
    ),
)


@diagnostic_check("postgres")
async def stale_statistics() -> list[Finding]:
    rows = await fetch(
        """
        SELECT schemaname || '.' || relname AS name,
            n_live_tup AS rows, n_mod_since_analyze AS modified
        FROM pg_catalog.pg_stat_user_tables
        WHERE n_live_tup >= $1 AND n_mod_since_analyze > n_live_tup * $2::float8
        ORDER BY n_mod_since_analyze DESC
        """,
        STALE_STATS_MIN_ROWS,
        STALE_STATS_RATIO,
    )
    return listing("PG-STATS-002", "warning", "tables", rows)


#
# Settings
#

register_code(
    "PG-CONF-001",
    CodeInfo(
        title="Settings left at their defaults",
        description="{count} performance settings are at their built-in defaults.",
        explanation=(
            "The built-in defaults are sized for a small machine with spinning "
            "disks. With them Postgres uses little memory for caching, sorts "
            "and hash joins, and avoids index scans. Ignore this if the values "
            "were chosen on purpose."
        ),
        remediation=(
            "Size the listed settings for the server's memory and storage, "
            "e.g. with https://pgtune.leopard.in.ua (for SSDs, "
            "`random_page_cost = 1.1`). On a managed database change them "
            "in its parameter group."
        ),
    ),
)


@diagnostic_check("postgres")
async def default_settings() -> list[Finding]:
    rows = await fetch(
        """
        SELECT name, current_setting(name) AS value
        FROM pg_catalog.pg_settings
        WHERE name = ANY($1) AND setting = boot_val
        ORDER BY name
        """,
        TUNED_SETTINGS,
    )
    return listing("PG-CONF-001", "info", "settings", rows)


#
# Vacuum
#

register_code(
    "PG-VAC-001",
    CodeInfo(
        title="Autovacuum is not keeping up",
        description="{count} tables have a high share of dead rows.",
        explanation=(
            "Dead rows are left behind by updates and deletes until vacuum "
            "removes them. These tables have far more than autovacuum should "
            "allow, so they bloat and queries read more pages than needed. "
            "Long-running transactions also prevent cleanup."
        ),
        remediation=(
            "Run `VACUUM (VERBOSE, ANALYZE) <table>;`, end long-running "
            "transactions (see PG-ACT-001) and consider more autovacuum "
            "workers or a lower `autovacuum_vacuum_cost_delay`."
        ),
    ),
)


@diagnostic_check("postgres")
async def dead_tuples() -> list[Finding]:
    rows = await fetch(
        """
        SELECT schemaname || '.' || relname AS name,
            n_live_tup AS live, n_dead_tup AS dead,
            last_autovacuum::text AS last_autovacuum
        FROM pg_catalog.pg_stat_user_tables
        WHERE n_dead_tup >= $1 AND n_dead_tup > n_live_tup * $2::float8
        ORDER BY n_dead_tup DESC
        """,
        DEAD_TUPLES_MIN,
        DEAD_TUPLES_RATIO,
    )
    return listing("PG-VAC-001", "warning", "tables", rows)


register_code(
    "PG-VAC-002",
    CodeInfo(
        title="Transaction ID wraparound approaching",
        description="{count} databases have old unfrozen transaction IDs.",
        explanation=(
            "Postgres has about 2.1 billion transaction IDs before they wrap "
            "around. Vacuum freezes old rows to make IDs reusable. If it "
            "can't, Postgres eventually stops accepting writes to protect "
            "the data. Long-running transactions, abandoned replication slots "
            "and prepared transactions block freezing."
        ),
        remediation=(
            "Find what blocks freezing (long transactions, "
            "`pg_replication_slots`, `pg_prepared_xacts`) and run "
            "`VACUUM (FREEZE, VERBOSE);` in the listed databases."
        ),
    ),
)


@diagnostic_check("postgres")
async def xid_wraparound() -> list[Finding]:
    rows = await fetch(
        """
        SELECT datname AS name, age(datfrozenxid) AS age
        FROM pg_catalog.pg_database
        WHERE datallowconn AND age(datfrozenxid) >= $1
        ORDER BY age(datfrozenxid) DESC
        """,
        XID_AGE_WARNING,
    )
    severity: Severity = "warning"
    if any(r["age"] >= XID_AGE_CRITICAL for r in rows):
        severity = "critical"
    return listing("PG-VAC-002", severity, "databases", rows)


#
# Indexes
#

register_code(
    "PG-IDX-001",
    CodeInfo(
        title="Invalid indexes",
        description="{count} indexes are invalid.",
        explanation=(
            "An index is left invalid when `CREATE INDEX CONCURRENTLY` or "
            "`REINDEX CONCURRENTLY` fails. Queries don't use it, but every "
            "write still updates it, and a unique index may not enforce "
            "uniqueness."
        ),
        remediation=(
            "Run `REINDEX INDEX CONCURRENTLY <index>;`, or drop and recreate it."
        ),
    ),
)


@diagnostic_check("postgres")
async def invalid_indexes() -> list[Finding]:
    rows = await fetch(
        """
        SELECT n.nspname || '.' || c.relname AS name
        FROM pg_catalog.pg_index i
        JOIN pg_catalog.pg_class c ON c.oid = i.indexrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT i.indisvalid
        ORDER BY 1
        """
    )
    return listing("PG-IDX-001", "warning", "indexes", [r["name"] for r in rows])


register_code(
    "PG-IDX-002",
    CodeInfo(
        title="Large tables read by sequential scans",
        description="{count} large tables are mostly read by sequential scans.",
        explanation=(
            "Each sequential scan reads the whole table. On large tables this "
            "usually means an index is missing, or that the planner doesn't "
            "use it because of outdated statistics." + STATS_SINCE
        ),
        remediation=(
            "Find the queries reading these tables (`pg_stat_statements`, "
            "slow query log) and check them with `EXPLAIN ANALYZE`."
        ),
    ),
)


@diagnostic_check("postgres")
async def sequential_scans() -> list[Finding]:
    rows = await fetch(
        """
        SELECT s.schemaname || '.' || s.relname AS name,
            s.seq_scan, coalesce(s.idx_scan, 0) AS idx_scan,
            pg_size_pretty(c.relpages::bigint * 8192) AS size
        FROM pg_catalog.pg_stat_user_tables s
        JOIN pg_catalog.pg_class c ON c.oid = s.relid
        WHERE c.relpages >= $1 AND s.seq_scan >= $2
        AND s.seq_scan > coalesce(s.idx_scan, 0)
        ORDER BY s.seq_tup_read DESC
        """,
        SEQ_SCAN_MIN_PAGES,
        SEQ_SCAN_MIN_COUNT,
    )
    return listing("PG-IDX-002", "warning", "tables", rows)


register_code(
    "PG-IDX-003",
    CodeInfo(
        title="Unused indexes",
        description="{count} large indexes have never been used.",
        explanation=(
            "These indexes take space and slow down every write, but no query "
            "has used them. Unique indexes are not listed, because they "
            "enforce constraints." + STATS_SINCE
        ),
        remediation=(
            "If an index is not needed (also on replicas, which have their "
            "own counters), drop it with `DROP INDEX CONCURRENTLY <index>;`."
        ),
    ),
)


@diagnostic_check("postgres")
async def unused_indexes() -> list[Finding]:
    rows = await fetch(
        """
        SELECT s.schemaname || '.' || s.indexrelname AS name,
            pg_size_pretty(c.relpages::bigint * 8192) AS size
        FROM pg_catalog.pg_stat_user_indexes s
        JOIN pg_catalog.pg_class c ON c.oid = s.indexrelid
        JOIN pg_catalog.pg_index i ON i.indexrelid = s.indexrelid
        WHERE s.idx_scan = 0 AND NOT i.indisunique AND c.relpages >= $1
        ORDER BY c.relpages DESC
        """,
        UNUSED_INDEX_MIN_PAGES,
    )
    return listing("PG-IDX-003", "info", "indexes", rows)


#
# Activity
#

register_code(
    "PG-ACT-001",
    CodeInfo(
        title="Long-running queries or transactions",
        description="{count} sessions have run a query or transaction for too long.",
        explanation=(
            "Long transactions hold locks and stop vacuum from removing dead "
            "rows, so tables bloat. Sessions `idle in transaction` are usually "
            "a client that opened a transaction and never finished it."
        ),
        remediation=(
            "Find the client by `application_name` and `client_addr` in "
            "`pg_stat_activity`. If it's stuck, end it with "
            "`SELECT pg_terminate_backend(<pid>);`. Setting "
            "`idle_in_transaction_session_timeout` prevents this."
        ),
    ),
)


@diagnostic_check("postgres")
async def long_running() -> list[Finding]:
    # No query text: it may contain data the dashboard shouldn't show
    rows = await fetch(
        """
        SELECT pid, state, datname AS database, application_name,
            extract(epoch FROM now() - coalesce(xact_start, query_start))::int
                AS seconds
        FROM pg_catalog.pg_stat_activity
        WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()
        AND state <> 'idle'
        AND now() - coalesce(xact_start, query_start) > make_interval(secs => $1)
        ORDER BY seconds DESC
        """,
        LONG_RUNNING_SECONDS,
    )
    return listing("PG-ACT-001", "warning", "sessions", rows)


#
# Cache
#

register_code(
    "PG-CACHE-001",
    CodeInfo(
        title="Low buffer cache hit ratio",
        description="Only {ratio:.0%} of reads in {database} are served from memory.",
        explanation=(
            "Postgres reads most data from disk instead of its buffer cache, "
            "which makes queries slow. The data that queries use doesn't fit "
            "into `shared_buffers`, or queries read more than they need "
            "(see PG-IDX-002)." + STATS_SINCE
        ),
        remediation=(
            "Increase `shared_buffers` (about 25% of memory is common) or the "
            "server's memory, and look for queries reading whole tables."
        ),
    ),
)


@diagnostic_check("postgres")
async def cache_hit_ratio() -> list[Finding]:
    rows = await fetch(
        """
        SELECT datname AS database, blks_hit::float / (blks_hit + blks_read) AS ratio
        FROM pg_catalog.pg_stat_database
        WHERE datname = current_database() AND blks_hit + blks_read >= $1
        """,
        CACHE_MIN_BLOCKS,
    )
    return [
        Finding(code="PG-CACHE-001", severity="warning", component="postgres", params=r)
        for r in rows
        if r["ratio"] < CACHE_HIT_MIN_RATIO
    ]
