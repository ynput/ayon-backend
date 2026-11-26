import time

from ayon_server.cli import app
from ayon_server.entity_search import ENTITY_TYPES, index_entities
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres

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
    """Empty and backfill the entity_search table of a project.

    Prints the row counts, timing and sizes.
    """
    await ayon_init(extensions=False)

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        await Postgres.execute("TRUNCATE entity_search")

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
