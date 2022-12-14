from typing import Any

import asyncpg
import asyncpg.pool
import asyncpg.transaction

from openpype.config import pypeconfig
from openpype.utils import EntityID, json_dumps, json_loads


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    shutting_down: bool = False
    pool: asyncpg.pool.Pool | None = None
    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError
    UndefinedTableError = asyncpg.exceptions.UndefinedTableError
    Connection = asyncpg.Connection
    Transaction = asyncpg.transaction.Transaction

    @classmethod
    def acquire(cls) -> asyncpg.Connection:
        """Acquire a connection from the pool."""
        if cls.pool is None:
            raise ConnectionError
        return cls.pool.acquire()

    @classmethod
    async def init_connection(self, conn) -> None:
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
    async def connect(cls) -> None:
        """Create a PostgreSQL connection pool."""
        if cls.shutting_down:
            print("Unable to connect to Postgres while shutting down.")
            return
        cls.pool = await asyncpg.create_pool(
            pypeconfig.postgres_url, init=cls.init_connection
        )

    @classmethod
    async def shutdown(cls) -> None:
        """Close the PostgreSQL connection pool."""
        if cls.pool is not None:
            await cls.pool.close()
            cls.pool = None
            cls.shutting_down = True

    @classmethod
    async def execute(cls, query: str, *args: Any) -> str:
        """Execute a SQL query and return a status (e.g. 'INSERT 0 2')"""
        if cls.pool is None:
            raise ConnectionError
        async with cls.pool.acquire() as connection:
            return await connection.execute(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args: Any):
        """Run a query and return the results as a list of Record."""
        if cls.pool is None:
            raise ConnectionError
        async with cls.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    @classmethod
    async def iterate(cls, query: str, *args: Any, transaction=None):
        """Run a query and return a generator yielding resulting rows records."""
        if transaction and transaction != cls:
            statement = await transaction.prepare(query)
            async for record in statement.cursor(*args):
                yield record
            return

        if cls.pool is None:
            raise ConnectionError

        async with cls.pool.acquire() as connection:
            async with connection.transaction():
                statement = await connection.prepare(query)
                async for record in statement.cursor(*args):
                    yield record
