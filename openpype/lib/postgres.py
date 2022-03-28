import asyncpg
import asyncpg.pool

from openpype.config import pypeconfig


class Postgres:
    pool: asyncpg.pool.Pool | None = None
    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError

    @classmethod
    @property
    def acquire(cls):
        return cls.pool.acquire

    @classmethod
    async def connect(cls):
        """Create a PostgreSQL connection pool."""
        cls.pool = await asyncpg.create_pool(pypeconfig.postgres_url)

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
