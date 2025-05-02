import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import asyncpg
import asyncpg.pool
from asyncpg.exceptions import TooManyConnectionsError
from asyncpg.pool import PoolConnectionProxy

from ayon_server.config import ayonconfig
from ayon_server.exceptions import ServiceUnavailableException
from ayon_server.logging import logger

from .postgres_setup import postgres_setup

if TYPE_CHECKING:
    Connection = PoolConnectionProxy[Any]
    from asyncpg.prepared_stmt import PreparedStatement
else:
    Connection = PoolConnectionProxy


#
# Context variable to store the current connection
#

_current_connection: ContextVar["PoolConnectionProxy | None"] = ContextVar(  # type: ignore[type-arg]
    "_current_connection", default=None
)

#
# Postgres acccess
#


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    shutting_down: bool = False
    _pool: asyncpg.pool.Pool | None = None  # type: ignore[type-arg]

    # Shorthand for asyncpg exceptions
    # so we when we need to catch them, we don't need to import them
    # from asyncpg over and over again

    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    IntegrityConstraintViolationError = (
        asyncpg.exceptions.IntegrityConstraintViolationError
    )  # noqa: E501
    NotNullViolationError = asyncpg.exceptions.NotNullViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError
    UndefinedTableError = asyncpg.exceptions.UndefinedTableError

    #
    # Connection pool lifecycle
    #

    @classmethod
    def get_available_connections(cls) -> int:
        """Return a number of connections available for use"""
        if not cls._pool:
            return 0
        max_size = cls._pool.get_max_size()
        current_size = cls._pool.get_size()
        idle_size = cls._pool.get_idle_size()
        return max_size - (current_size - idle_size)

    @classmethod
    async def connect(cls) -> None:
        """Create a PostgreSQL connection pool."""

        if cls.shutting_down:
            logger.warning(
                "Unable to connect to Postgres while shutting down.", nodb=True
            )
            return
        cls._pool = await asyncpg.create_pool(
            ayonconfig.postgres_url,
            min_size=10,
            max_size=ayonconfig.postgres_pool_size,
            max_inactive_connection_lifetime=20,
            init=postgres_setup,
        )

    @classmethod
    async def shutdown(cls) -> None:
        """Close the PostgreSQL connection pool."""
        if cls._pool is not None:
            try:
                await asyncio.wait_for(cls._pool.close(), timeout=5)
            except TimeoutError:
                logger.error("Timeout closing Postgres connection pool.", nodb=True)
                cls._pool.terminate()
            finally:
                cls._pool = None
                cls.shutting_down = True

    #
    # Get connection / transaction
    #

    @classmethod
    @asynccontextmanager
    async def acquire(
        cls, timeout: int | None = None
    ) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool."""

        if cls._pool is None:
            raise ConnectionError("Connection pool is not initialized.")

        if timeout is None:
            timeout = ayonconfig.postgres_pool_timeout

        try:
            connection_proxy = await cls._pool.acquire(timeout=timeout)
        except TimeoutError:
            raise ServiceUnavailableException("Database pool timeout")
        except TooManyConnectionsError:
            raise ServiceUnavailableException("Database pool is full")

        token = _current_connection.set(connection_proxy)

        try:
            yield connection_proxy
        finally:
            _current_connection.reset(token)
            await cls._pool.release(connection_proxy)

    @classmethod
    @asynccontextmanager
    async def _connection_resolver(cls) -> AsyncGenerator[Connection, None]:
        """
        Resolve the current connection from the context variable or acquire a new one.
        If the connection is not available, create a new one.
        """
        conn = _current_connection.get()
        if conn is not None:
            yield conn
            return

        if cls._pool is None:
            await cls.connect()
            assert cls._pool is not None

        async with cls.acquire() as connection:
            yield connection

    @classmethod
    @asynccontextmanager
    async def transaction(cls) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool and start a transaction."""
        async with cls._connection_resolver() as connection:
            async with connection.transaction():
                yield connection

    @classmethod
    async def is_in_transaction(cls) -> bool:
        """Check if the current connection is in a transaction."""
        conn = _current_connection.get()
        if conn is None:
            return False
        return conn.is_in_transaction()

    #
    # Postgres query wrappers
    #

    @classmethod
    async def execute(cls, query: str, *args: Any, timeout: float = 60) -> str:
        """Execute a SQL query and return a status (e.g. 'INSERT 0 2')"""
        async with cls._connection_resolver() as connection:
            return await connection.execute(query, *args, timeout=timeout)

    @classmethod
    async def executemany(cls, query: str, *args: Any, timeout: float = 60) -> None:
        """Execute a SQL query with multiple parameters."""
        async with cls._connection_resolver() as connection:
            return await connection.executemany(query, *args, timeout=timeout)

    @classmethod
    async def fetch(cls, query: str, *args: Any, timeout: float = 60):
        """Run a query and return the results as a list of Record."""
        async with cls._connection_resolver() as connection:
            return await connection.fetch(query, *args, timeout=timeout)

    @classmethod
    async def fetchrow(cls, query: str, *args: Any, timeout: float = 60):
        """Run a query and return the first row as a Record."""
        async with cls._connection_resolver() as connection:
            return await connection.fetchrow(query, *args, timeout=timeout)

    @classmethod
    async def prepare(
        cls, query: str, *args: Any, timeout: float = 60
    ) -> "PreparedStatement":  # type: ignore[type-arg]
        """Prepare a statement"""
        async with cls._connection_resolver() as connection:
            if not connection.is_in_transaction():
                raise RuntimeError("Cannot prepare statement outside of a transaction")
            return await connection.prepare(query, *args, timeout=timeout)

    @classmethod
    async def iterate(
        cls,
        query: str,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run a query and return a generator yielding rows as dictionaries."""
        _ = kwargs
        async with cls._connection_resolver() as connection:
            if not connection.is_in_transaction():
                async with connection.transaction():
                    statement = await connection.prepare(query)
                    async for record in statement.cursor(*args):
                        yield dict(record)
            else:
                statement = await connection.prepare(query)
                async for record in statement.cursor(*args):
                    yield dict(record)
