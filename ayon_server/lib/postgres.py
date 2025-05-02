import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncpg
import asyncpg.pool
from asyncpg.exceptions import TooManyConnectionsError
from asyncpg.pool import PoolConnectionProxy

from ayon_server.config import ayonconfig
from ayon_server.exceptions import AyonException, ServiceUnavailableException

from .postgres_setup import postgres_setup

if TYPE_CHECKING:
    Connection = PoolConnectionProxy[Any]
else:
    Connection = PoolConnectionProxy


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    shutting_down: bool = False
    pool: asyncpg.pool.Pool | None = None  # type: ignore

    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError
    UndefinedTableError = asyncpg.exceptions.UndefinedTableError

    @classmethod
    @asynccontextmanager
    async def acquire(
        cls, timeout: int | None = None
    ) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool."""

        if cls.pool is None:
            raise ConnectionError("Connection pool is not initialized.")

        if timeout is None:
            timeout = ayonconfig.postgres_pool_timeout

        try:
            connection_proxy = await cls.pool.acquire(timeout=timeout)
        except TimeoutError:
            raise ServiceUnavailableException("Database pool timeout")
        except TooManyConnectionsError:
            raise ServiceUnavailableException("Database pool is full")

        try:
            yield connection_proxy
        finally:
            await cls.pool.release(connection_proxy)

    @classmethod
    def get_available_connections(cls) -> int:
        """Return a number of connections available for use"""
        if not cls.pool:
            return 0
        max_size = cls.pool.get_max_size()
        current_size = cls.pool.get_size()
        idle_size = cls.pool.get_idle_size()
        return max_size - (current_size - idle_size)

    @classmethod
    async def connect(cls) -> None:
        """Create a PostgreSQL connection pool."""

        if cls.shutting_down:
            print("Unable to connect to Postgres while shutting down.")
            return
        cls.pool = await asyncpg.create_pool(
            ayonconfig.postgres_url,
            min_size=10,
            max_size=ayonconfig.postgres_pool_size,
            max_inactive_connection_lifetime=20,
            init=postgres_setup,
        )

    @classmethod
    async def shutdown(cls) -> None:
        """Close the PostgreSQL connection pool."""
        if cls.pool is not None:
            try:
                await asyncio.wait_for(cls.pool.close(), timeout=5)
            except TimeoutError:
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
    async def fetchrow(cls, query: str, *args: Any, timeout: float = 60):
        """Run a query and return the first row as a Record."""
        if cls.pool is None:
            raise ConnectionError
        async with cls.acquire() as connection:
            return await connection.fetchrow(query, *args, timeout=timeout)

    @classmethod
    async def iterate(
        cls,
        query: str,
        *args: Any,
        transaction: Connection | None = None,
    ):
        """Run a query and return a generator yielding resulting rows records."""
        if transaction:  # temporary. will be fixed
            if not transaction.is_in_transaction():
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
