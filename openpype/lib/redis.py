import aioredis

from openpype.config import pypeconfig


class Redis:
    redis_pool = None

    @classmethod
    async def connect(cls) -> None:
        """Create a Redis connection pool"""
        cls.redis_pool = aioredis.from_url(pypeconfig.redis_url)

    @classmethod
    async def get(cls, namespace: str, key: str) -> str:
        if not cls.redis_pool:
            await cls.connect()
        return await cls.redis_pool.get(namespace + "-" + key)

    @classmethod
    async def set(cls, namespace: str, key: str, value: str, ttl: int = 0):
        """Create/update a record in Redis

        Optional ttl argument may be provided to set expiration time.
        """
        if not cls.redis_pool:
            await cls.connect()
        command = ["set", namespace + "-" + key, value]
        if ttl:
            command.extend(["ex", ttl])

        return await cls.redis_pool.execute_command(*command)

    @classmethod
    async def delete(cls, namespace: str, key: str):
        if not cls.redis_pool:
            await cls.connect()
        return await cls.redis_pool.delete(namespace + "-" + key)

    @classmethod
    async def incr(cls, namespace: str, key: str):
        if not cls.redis_pool:
            await cls.connect()
        return await cls.redis_pool.incr(namespace + "-" + key)
