"""Fill the trait columns of existing representations.

Migration 00000017 adds `trait_ids` and `trait_fields` with the trigger
that keeps them in sync, but does not touch existing rows, so the server
starts right away. This worker fills them in small batches and then
builds the GIN indexes with CREATE INDEX CONCURRENTLY, so representations
stay writable the whole time.

Until a project is done, trait filters on it return incomplete results
and run without the index.

A project is done when both indexes exist and are valid. New projects get
the indexes from schema.project.sql and are skipped. Rows are found by
their state (traits present, trait_ids empty), so the work survives
restarts and runs again safely. Only one server instance does it at a
time (session advisory lock).
"""

import asyncio

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback, logger

LOCK_KEY = "traits:backfill"
BATCH_SIZE = 500
BATCH_PAUSE = 0.05
CHECK_INTERVAL = 3600
START_DELAY = 30

INDEXES = {
    "representation_trait_ids_idx": "USING gin(trait_ids)",
    "representation_trait_fields_idx": "USING gin(trait_fields jsonb_path_ops)",
}

PENDING_SCHEMAS_QUERY = """
    SELECT ns.nspname AS project_schema
    FROM pg_namespace ns
    JOIN pg_class cl
      ON cl.relnamespace = ns.oid
      AND cl.relname = 'representations'
      AND cl.relkind = 'r'
    WHERE
      ns.nspname LIKE 'project\\_%'
      AND EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = cl.oid AND attname = 'trait_fields' AND NOT attisdropped
      )
      AND (
        SELECT count(*) FROM pg_index i
        JOIN pg_class ic ON ic.oid = i.indexrelid
        WHERE i.indrelid = cl.oid AND i.indisvalid AND ic.relname = ANY($1)
      ) < $2
    ORDER BY ns.nspname
"""

INDEX_STATE_QUERY = """
    SELECT ic.relname AS name, i.indisvalid AS valid
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class cl ON cl.oid = i.indrelid
    JOIN pg_namespace ns ON ns.oid = cl.relnamespace
    WHERE ns.nspname = $1 AND cl.relname = 'representations'
      AND ic.relname = ANY($2)
"""


def batch_query(schema: str) -> str:
    # Rows with traits always get at least one id, so an empty trait_ids
    # next to non-empty traits means the row has not been filled yet.
    # The trigger does not fire: `traits` is not in the SET list.
    return f"""
        WITH batch AS (
            SELECT id FROM {schema}.representations
            WHERE $1::UUID IS NULL OR id > $1::UUID
            ORDER BY id
            LIMIT {BATCH_SIZE}
        ),
        filled AS (
            UPDATE {schema}.representations r SET
                trait_ids = public.trait_ids_of(r.traits),
                trait_fields = public.trait_fields_of(r.traits)
            FROM batch
            WHERE r.id = batch.id
              AND r.traits IS NOT NULL
              AND r.trait_ids = ARRAY[]::VARCHAR[]
              AND r.traits <> '{{}}'::JSONB
            RETURNING r.id
        )
        SELECT
            (SELECT id FROM batch ORDER BY id DESC LIMIT 1) AS last_id,
            (SELECT count(*) FROM filled) AS filled
    """


class TraitColumnsBackfill(BackgroundWorker):
    async def run(self) -> None:
        await asyncio.sleep(START_DELAY)
        while True:
            try:
                await self.process()
            except asyncio.CancelledError:
                raise
            except Exception:
                log_traceback("Trait columns backfill failed")
            # Catches projects imported from older backups
            await asyncio.sleep(CHECK_INTERVAL)

    async def process(self) -> None:
        async with Postgres.acquire(force_new=True) as conn:
            locked = await conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtextextended($1, 0))", LOCK_KEY
            )
            if not locked:
                return
            try:
                rows = await conn.fetch(
                    PENDING_SCHEMAS_QUERY, list(INDEXES), len(INDEXES)
                )
                for row in rows:
                    await self.process_schema(conn, row["project_schema"])
            finally:
                await conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))", LOCK_KEY
                )

    async def process_schema(self, conn, project_schema: str) -> None:
        schema = '"' + project_schema.replace('"', '""') + '"'
        logger.info(f"Filling trait columns in {project_schema}")

        query = batch_query(schema)
        last_id = None
        total = 0
        while True:
            row = await conn.fetchrow(query, last_id, timeout=60)
            if row is None or row["last_id"] is None:
                break
            last_id = row["last_id"]
            total += row["filled"]
            await asyncio.sleep(BATCH_PAUSE)

        # A failed CONCURRENTLY build leaves an invalid index behind
        states = {
            r["name"]: r["valid"]
            for r in await conn.fetch(INDEX_STATE_QUERY, project_schema, list(INDEXES))
        }
        for name, definition in INDEXES.items():
            if states.get(name):
                continue
            if name in states:
                await conn.execute(
                    f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.{name}", timeout=None
                )
            await conn.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {schema}.representations {definition}",
                timeout=None,
            )

        logger.info(
            f"Trait columns of {project_schema} are ready "
            f"({total} representations filled)"
        )


trait_columns_backfill = TraitColumnsBackfill()
