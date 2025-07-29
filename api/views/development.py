from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres

# Reset the views table in the database for development purposes.

queries = [
    "DROP TABLE IF EXISTS views CASCADE;",
    """
    CREATE TABLE IF NOT EXISTS views(
    id UUID NOT NULL PRIMARY KEY,
    view_type VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    owner VARCHAR,
    visibility VARCHAR NOT NULL CHECK (visibility IN ('public', 'private')),
    personal BOOLEAN NOT NULL DEFAULT FALSE,

    access JSONB NOT NULL DEFAULT '{}'::JSONB,
    data JSONB NOT NULL DEFAULT '{}'::JSONB);""",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS unique_personal_view
    ON views(view_type, owner) WHERE personal;""",
    "CREATE INDEX IF NOT EXISTS view_type_idx ON views(view_type);"
    "CREATE INDEX IF NOT EXISTS view_owner_idx ON views(owner);",
]


async def recreate_views_tables():
    """Recreate the views table in the database."""

    projects = await get_project_list()

    async with Postgres.transaction():
        for query in queries:
            await Postgres.execute(query)

        for project in projects:
            await Postgres.set_project_schema(project.name)
            for query in queries:
                await Postgres.execute(query)
