import asyncpg
import asyncpg.pool

from openpype.config import pypeconfig
from openpype.utils import EntityID, json_dumps, json_loads


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    pool: asyncpg.pool.Pool | None = None
    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError
    UndefinedTableError = asyncpg.exceptions.UndefinedTableError

    @classmethod
    @property
    def acquire(cls):
        """Acquire a connection from the pool."""
        return cls.pool.acquire

    @classmethod
    async def init_connection(self, conn):
        """Set up the connection pool"""
        await conn.set_type_codec(
            "jsonb",
            encoder=json_dumps,
            decoder=json_loads,
            schema="pg_catalog",
        )
        await conn.set_type_codec(
            "uuid",
            encoder=lambda x: EntityID.parse(x, True),
            decoder=lambda x: EntityID.parse(x, True),
            schema="pg_catalog",
        )

    @classmethod
    async def connect(cls):
        """Create a PostgreSQL connection pool."""
        cls.pool = await asyncpg.create_pool(
            pypeconfig.postgres_url, init=cls.init_connection
        )

    @classmethod
    async def execute(cls, query, *args):
        """Execute a SQL query and return a status (e.g. 'INSERT 0 2')"""
        async with cls.pool.acquire() as connection:
            return await connection.execute(query, *args)

    @classmethod
    async def fetch(cls, query, *args):
        """Run a query and return the results as a list of Record."""
        async with cls.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    @classmethod
    async def iterate(cls, query, *args, transaction=None):
        """Run a query and return a generator yielding resulting rows records."""
        if transaction:
            statement = await transaction.prepare(query)
            async for record in transaction.fetch(query, *args):
                yield record
            return

        async with cls.pool.acquire() as connection:
            async with connection.transaction():
                statement = await connection.prepare(query)
                async for record in statement.cursor(*args):
                    yield record
