import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import urlparse

import asyncpg
import asyncpg.pool
from asyncpg.exceptions import QueryCanceledError, TooManyConnectionsError
from asyncpg.pool import PoolConnectionProxy

from ayon_server.config import ayonconfig
from ayon_server.exceptions import ServiceUnavailableException
from ayon_server.logging import log_traceback, logger

from .postgres_setup import postgres_setup

if TYPE_CHECKING:
    Connection = PoolConnectionProxy[Any]
    from asyncpg.prepared_stmt import PreparedStatement
else:
    Connection = PoolConnectionProxy


class DBConnectionInfo(TypedDict):
    user: str
    password: str
    host: str
    port: int
    database: str


def get_pg_connection_info() -> DBConnectionInfo:
    conn_string = ayonconfig.postgres_url
    result = urlparse(conn_string)
    # Extract the relevant components
    user = result.username
    password = result.password
    host = result.hostname
    port = result.port or 5432
    database = result.path[1:]  # Remove the leading '/'
    assert user and password and host and database and port, (
        "Postgres connection string is not valid"
    )

    return DBConnectionInfo(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )


#
# Context variable to store the current connection
#

_current_connection: ContextVar["Connection | None"] = ContextVar(
    "_current_connection", default=None
)

_current_project: ContextVar[str | None] = ContextVar("_current_project", default=None)

CommitHook = Callable[[], Awaitable[Any]]

# Hooks of the current (outermost) transaction, run after it commits
_commit_hooks: ContextVar[list[CommitHook] | None] = ContextVar(
    "_commit_hooks", default=None
)


async def _run_commit_hooks(hooks: list[CommitHook]) -> None:
    # The data is already committed: one failing hook must not skip the others
    # or turn the request into an error
    for hook in hooks:
        try:
            await hook()
        except Exception:
            log_traceback("Post-commit hook failed")


#
# Postgres acccess
#


class Postgres:
    """Postgres database connection.

    Provides an interface for interacting with a Postgres database.
    """

    shutting_down: bool = False
    pool: asyncpg.pool.Pool | None = None

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
    LockNotAvailableError = asyncpg.exceptions.LockNotAvailableError

    #
    # Connection pool lifecycle
    #

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
            logger.warning(
                "Unable to connect to Postgres while shutting down.", nodb=True
            )
            return
        cls.pool = await asyncpg.create_pool(
            ayonconfig.postgres_url,
            min_size=0,
            init_size=min(10, ayonconfig.postgres_pool_size),
            max_size=ayonconfig.postgres_pool_size,
            max_inactive_connection_lifetime=20,
            init=postgres_setup,
            # Resolvers build ad-hoc SQL (conditions inlined into the query
            # text, not parameterized), so almost every request gets its own
            # distinct plan - postgres never amortizes JIT compilation across
            # repeated executions the way a prepared-statement app would.
            server_settings={"jit": "off"},
        )

    @classmethod
    async def shutdown(cls) -> None:
        """Close the PostgreSQL connection pool."""
        if cls.pool is not None:
            try:
                await asyncio.wait_for(cls.pool.close(), timeout=5)
            except TimeoutError:
                logger.error("Timeout closing Postgres connection pool.", nodb=True)
                cls.pool.terminate()
            finally:
                cls.pool = None
                cls.shutting_down = True

    #
    # Get connection / transaction
    #

    @classmethod
    async def _pool_acquire(cls, timeout: float | None = None) -> Connection:
        """Take a connection from the pool, or fail with 503 when none is free.

        The caller must release it. Sets no context, so `iterate` can use it.
        """
        assert cls.pool is not None, "Connection pool is not initialized."
        if timeout is None:
            timeout = ayonconfig.postgres_pool_timeout
        try:
            return await cls.pool.acquire(timeout=timeout)
        except TimeoutError:
            raise ServiceUnavailableException("Database pool timeout")
        except TooManyConnectionsError:
            raise ServiceUnavailableException("Database pool is full")

    @classmethod
    @asynccontextmanager
    async def acquire(
        cls,
        *,
        timeout: int | None = None,
        force_new: bool = False,
    ) -> AsyncGenerator[Connection]:
        """Acquire a connection from the pool."""
        conn = _current_connection.get()
        if conn is not None and not force_new:
            yield conn
            return

        assert cls.pool is not None, "Connection pool is not initialized."
        connection_proxy = await cls._pool_acquire(timeout)
        token = _current_connection.set(connection_proxy)

        try:
            yield connection_proxy
        finally:
            _current_connection.reset(token)
            await cls.pool.release(connection_proxy)

    @classmethod
    @asynccontextmanager
    async def transaction(
        cls,
        *,
        timeout: int | None = None,
        force_new: bool = False,
    ) -> AsyncGenerator[Connection]:
        """Acquire a connection from the pool and start a transaction."""
        async with cls.acquire(timeout=timeout, force_new=force_new) as connection:
            if connection.is_in_transaction():
                # If we are already in a transaction, just yield the connection
                # force_new would use a new connection, so it would not be
                # in a transaction
                yield connection
            else:
                token = _current_project.set(None)
                hooks: list[CommitHook] = []
                hooks_token = _commit_hooks.set(hooks)
                try:
                    async with connection.transaction():
                        with logger.contextualize(transaction_id=id(connection)):
                            yield connection
                finally:
                    _commit_hooks.reset(hooks_token)
                    _current_project.reset(token)
                # Only reached when the transaction committed
                await _run_commit_hooks(hooks)

    @classmethod
    async def on_commit(cls, hook: CommitHook) -> None:
        """Run `hook` after the current transaction commits (now if there is none).

        Hooks can be added anywhere inside the transaction (also in nested
        `transaction()` blocks, which join the outer one). They run in the order
        they were added, after the outermost transaction commits, and are
        dropped on rollback.
        """
        hooks = _commit_hooks.get()
        conn = _current_connection.get()
        if hooks is not None and conn is not None and conn.is_in_transaction():
            hooks.append(hook)
        else:
            # Async only for this: callers outside a transaction (operations
            # refresh their views after it) need the hook done when it returns
            await hook()

    @classmethod
    async def is_in_transaction(cls) -> bool:
        """Check if the current connection is in a transaction."""
        conn = _current_connection.get()
        if conn is None:
            return False
        return conn.is_in_transaction()

    @classmethod
    async def advisory_xact_lock(cls, key: str, *, shared: bool = False) -> None:
        """Wait for an advisory lock on `key`, held until the transaction ends.

        Keys are hashed strings, so callers share a single key space
        (use a "<domain>:<id>" prefix to avoid clashes).
        Shared locks only block, and are blocked by, exclusive ones.
        """
        fn = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        async with cls.acquire() as connection:
            # outside a transaction the lock would be released immediately
            assert connection.is_in_transaction(), (
                "Advisory xact lock requires a transaction"
            )
            await connection.execute(
                f"SELECT {fn}(hashtextextended($1, 0))", key, timeout=60
            )

    @classmethod
    def get_current_project_name(cls) -> str | None:
        """Return the name of the current project schema."""
        return _current_project.get()

    #
    # Postgres query wrappers
    #

    @classmethod
    async def execute(cls, query: str, *args: Any, timeout: float = 60) -> str:
        """Execute a SQL query and return a status (e.g. 'INSERT 0 2')"""
        async with cls.acquire() as connection:
            return await connection.execute(query, *args, timeout=timeout)

    @classmethod
    async def executemany(cls, query: str, *args: Any, timeout: float = 60) -> None:
        """Execute a SQL query with multiple parameters."""
        async with cls.acquire() as connection:
            return await connection.executemany(query, *args, timeout=timeout)

    @classmethod
    async def fetch(cls, query: str, *args: Any, timeout: float | None = 60):
        """Run a query and return the results as a list of Record."""
        async with cls.acquire() as connection:
            return await connection.fetch(query, *args, timeout=timeout)

    @classmethod
    async def fetchrow(cls, query: str, *args: Any, timeout: float = 60):
        """Run a query and return the first row as a Record."""
        async with cls.acquire() as connection:
            return await connection.fetchrow(query, *args, timeout=timeout)

    @classmethod
    async def prepare(
        cls, query: str, *args: Any, timeout: float = 60
    ) -> "PreparedStatement[Any]":
        """Prepare a statement"""
        async with cls.acquire() as connection:
            assert connection.is_in_transaction(), (
                "Cannot prepare statement outside of a transaction"
            )
            return await connection.prepare(query, *args, timeout=timeout)

    @classmethod
    async def set_project_schema(cls, project_name: str) -> None:
        """Set the search path to the project schema."""
        if cls.get_current_project_name() == project_name:
            return
        async with cls.acquire() as conn:
            assert conn.is_in_transaction(), (
                "Cannot set project schema outside of a transaction"
            )
            await conn.execute(f"SET LOCAL search_path TO project_{project_name}")
            _current_project.set(project_name)

    @classmethod
    async def set_public_schema(cls) -> None:
        """Set the search path to the public schema."""
        if cls.get_current_project_name() is None:
            return
        async with cls.acquire() as conn:
            assert conn.is_in_transaction(), (
                "Cannot set public schema outside of a transaction"
            )
            await conn.execute("SET LOCAL search_path TO public")
            _current_project.set(None)

    @classmethod
    async def iterate(
        cls,
        query: str,
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any]]:
        """Run a query and return a generator yielding rows as dictionaries.

        `timeout` is the statement timeout in seconds (0 for no limit,
        default `postgres_read_timeout`). It is ignored inside a transaction,
        which keeps its own settings.
        """
        if timeout is None:
            timeout = ayonconfig.postgres_read_timeout
        _ = kwargs  # collect unused kwargs (such as legacy "conn" argument)
        assert cls.pool is not None, "Connection pool is not initialized. "

        # Do not use context manager here:
        # Never set() a ContextVar in a context that may yield to caller
        # and then try to reset() it as async context may change

        conn = _current_connection.get()
        if conn is not None and conn.is_in_transaction():
            # Run in the caller's transaction, so it sees its locks and writes.
            # Only then: a cursor opened outside one would need its own transaction,
            # left open on the shared connection if the caller stops iterating early.
            statement = await conn.prepare(query)
            async for record in statement.cursor(*args):
                yield dict(record)
            return

        # Shed load instead of queueing forever when the pool is exhausted
        conn = await cls._pool_acquire()
        try:
            async with conn.transaction():
                # Nobody waits for a read this long: stop it, so abandoned
                # queries don't pile up on the database
                await conn.execute(
                    f"SET LOCAL statement_timeout = {int(timeout * 1000)}"
                )
                statement = await conn.prepare(query)
                async for record in statement.cursor(*args):
                    yield dict(record)
        except QueryCanceledError:
            raise ServiceUnavailableException("Database query timed out")
        finally:
            await cls.pool.release(conn)
