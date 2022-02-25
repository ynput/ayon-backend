import asyncpg

from nxtools import logging
from openpype.config import pypeconfig


class Postgres():
    pool = None
    ForeignKeyViolationError = asyncpg.exceptions.ForeignKeyViolationError
    UniqueViolationError = asyncpg.exceptions.UniqueViolationError

    @classmethod
    async def connect(cls):
        logging.info("Connecting to PostgreSQL")
        cls.pool = await asyncpg.create_pool(pypeconfig.postgres_url)
        cls.acquire = cls.pool.acquire

    @classmethod
    async def execute(cls, query, *args):
        async with cls.pool.acquire() as connection:
            return await connection.execute(query, *args)

    @classmethod
    async def fetch(cls, query, *args):
        async with cls.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    @classmethod
    async def iterate(cls, query, *args, transaction=None):
        if transaction:
            # TODO: use the same mechanism as in the default
            # (non-transactional) implementation
            # TODO: This is probably not needed at all
            # since iteration does not make much sense in transaction
            async for record in transaction.fetch(query, *args):
                yield record
            return

        async with cls.pool.acquire() as connection:
            async with connection.transaction():
                statement = await connection.prepare(query)
                async for record in statement.cursor(*args):
                    yield record
