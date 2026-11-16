import time

from ayon_server.cli import app
from ayon_server.entity_search import ENTITY_TYPES, index_entities
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres

# Experimental: moves to schemas/schema.project.sql and a migration
# once the shape is settled (#1285).
SCHEMA = """
DROP TABLE IF EXISTS entity_search;

CREATE TABLE entity_search (
    entity_id UUID PRIMARY KEY, -- for comments: the activity id
    entity_type VARCHAR NOT NULL,
    folder_id UUID NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    version_id UUID REFERENCES versions(id) ON DELETE CASCADE,
    activity_id UUID GENERATED ALWAYS AS
        (CASE WHEN entity_type = 'comment' THEN entity_id END) STORED
        REFERENCES activities(id) ON DELETE CASCADE,
    search_vector tsvector NOT NULL,
    updated_at TIMESTAMPTZ -- copied from the source row
);

CREATE INDEX entity_search_vector_idx ON entity_search USING gin(search_vector);
CREATE INDEX entity_search_folder_idx ON entity_search(folder_id);
CREATE INDEX entity_search_task_idx ON entity_search(task_id)
    WHERE task_id IS NOT NULL;
CREATE INDEX entity_search_product_idx ON entity_search(product_id)
    WHERE product_id IS NOT NULL;
CREATE INDEX entity_search_version_idx ON entity_search(version_id)
    WHERE version_id IS NOT NULL;
CREATE INDEX entity_search_activity_idx ON entity_search(activity_id)
    WHERE activity_id IS NOT NULL;
"""

SIZES = """
SELECT c.relname AS name, pg_relation_size(c.oid) AS size
FROM pg_class c
WHERE c.oid = to_regclass('entity_search')
OR c.oid IN (
    SELECT indexrelid FROM pg_index
    WHERE indrelid = to_regclass('entity_search')
)
ORDER BY c.relkind DESC, c.relname
"""


@app.command()
async def rebuild_entity_search(project_name: str, batch_size: int = 10000) -> None:
    """Drop, recreate and backfill the entity_search table of a project.

    Experimental. Prints the row counts, timing and sizes.
    """
    await ayon_init(extensions=False)

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        await Postgres.execute(SCHEMA)

    start = time.monotonic()
    for entity_type in ENTITY_TYPES:
        type_start = time.monotonic()
        count = await index_entities(project_name, entity_type, batch_size=batch_size)
        elapsed = time.monotonic() - type_start
        print(f"{entity_type:<10}{count:>10} rows {elapsed:>8.2f} s")
    print(f"{'total':<24}{time.monotonic() - start:>10.2f} s\n")

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        # Without statistics the planner ignores the GIN index
        await Postgres.execute("ANALYZE entity_search")
        sizes = await Postgres.fetch(SIZES)
    for row in sizes:
        print(f"{row['name']:<28}{row['size'] / 1024**2:>10.1f} MB")
