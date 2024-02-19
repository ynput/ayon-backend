import asyncio
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import asyncpg.pool
import asyncpg.transaction

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException, ServiceUnavailableException
from ayon_server.utils import EntityID, json_dumps, json_loads


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    default_acquire_timeout: int = 10

    shutting_down: bool = False
    pool: asyncpg.pool.Pool | None = None
    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError
    UndefinedTableError = asyncpg.exceptions.UndefinedTableError
    Connection = asyncpg.Connection
    Transaction = asyncpg.transaction.Transaction

    @classmethod
    @asynccontextmanager
    async def acquire(cls, timeout: int | None = None):
        """Acquire a connection from the pool."""

        if cls.pool is None:
            raise ConnectionError("Connection pool is not initialized.")

        if timeout is None:
            timeout = cls.default_acquire_timeout

        try:
            conn = await cls.pool.acquire(timeout=timeout)
        except asyncio.TimeoutError:
            raise ServiceUnavailableException("Database pool exhausted")

        try:
            yield conn
        finally:
            await cls.pool.release(conn)

    @classmethod
    async def init_connection(cls, conn) -> None:
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
    def get_available_connections(cls) -> int:
        """Return a number of connections available for use"""
        if not cls.pool:
            return 0
        max_size = Postgres.pool.get_max_size()
        current_size = Postgres.pool.get_size()
        idle_size = Postgres.pool.get_idle_size()
        return max_size - (current_size - idle_size)

    @classmethod
    async def connect(cls) -> None:
        """Create a PostgreSQL connection pool.

        By default, we use 24 as max_size, since default maximum
        connection value of postgres is 100 so, 25 is perfect for
        4 workers and a small reserve.
        """

        if cls.shutting_down:
            print("Unable to connect to Postgres while shutting down.")
            return
        cls.pool = await asyncpg.create_pool(
            ayonconfig.postgres_url,
            min_size=10,
            max_size=24,
            max_inactive_connection_lifetime=20,
            init=cls.init_connection,
        )

    @classmethod
    async def shutdown(cls) -> None:
        """Close the PostgreSQL connection pool."""
        if cls.pool is not None:
            try:
                await asyncio.wait_for(cls.pool.close(), timeout=5)
            except asyncio.TimeoutError:
                print("Timeout closing Postgres connection pool.")
                cls.pool.terminate()
            finally:
                cls.pool = None
                cls.shutting_down = True

    @classmethod
    async def execute(cls, query: str, *args: Any, timeout: float = 60) -> str:
        """Execute a SQL query and return a status (e.g. 'INSERT 0 2')"""
        if cls.pool is None:
            raise ConnectionError
        async with cls.acquire() as connection:
            return await connection.execute(query, *args, timeout=timeout)

    @classmethod
    async def fetch(cls, query: str, *args: Any, timeout: float = 60):
        """Run a query and return the results as a list of Record."""
        if cls.pool is None:
            raise ConnectionError
        async with cls.acquire() as connection:
            return await connection.fetch(query, *args, timeout=timeout)

    @classmethod
    async def iterate(
        cls,
        query: str,
        *args: Any,
        transaction: asyncpg.Connection | None = None,
    ):
        """Run a query and return a generator yielding resulting rows records."""
        if transaction and transaction != cls:  # temporary. will be fixed
            if not transaction.is_in_transaction:
                raise AyonException(
                    "Iterate called with a connection which is not in transaction."
                )
            statement = await transaction.prepare(query)
            async for record in statement.cursor(*args):
                yield record
            return

        if cls.pool is None:
            raise ConnectionError

        async with cls.acquire() as connection:
            async with connection.transaction():
                statement = await connection.prepare(query)
                async for record in statement.cursor(*args):
                    yield record
