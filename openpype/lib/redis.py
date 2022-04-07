import aioredis

from openpype.config import pypeconfig


class Redis:
    connected: bool = False
    redis_pool: aioredis.Redis

    @classmethod
    async def connect(cls) -> None:
        """Create a Redis connection pool"""
        cls.redis_pool = aioredis.from_url(pypeconfig.redis_url)
        cls.connected = True

    @classmethod
    async def get(cls, namespace: str, key: str) -> str:
        if not cls.connected:
            await cls.connect()
        return await cls.redis_pool.get(namespace + "-" + key)

    @classmethod
    async def set(cls, namespace: str, key: str, value: str, ttl: int = 0):
        """Create/update a record in Redis

        Optional ttl argument may be provided to set expiration time.
        """
        if not cls.connected:
            await cls.connect()
        command = ["set", namespace + "-" + key, value]
        if ttl:
            command.extend(["ex", str(ttl)])

        return await cls.redis_pool.execute_command(*command)

    @classmethod
    async def delete(cls, namespace: str, key: str):
        if not cls.connected:
            await cls.connect()
        return await cls.redis_pool.delete(namespace + "-" + key)

    @classmethod
    async def incr(cls, namespace: str, key: str):
        if not cls.connected:
            await cls.connect()
        return await cls.redis_pool.incr(namespace + "-" + key)

    @classmethod
    async def pubsub(cls):
        if not cls.connected:
            await cls.connect()
        return cls.redis_pool.pubsub()

    @classmethod
    async def publish(cls, message: str, channel: str | None = None):
        if not cls.connected:
            await cls.connect()
        if channel is None:
            channel = pypeconfig.redis_channel
        return await cls.redis_pool.publish(channel, message)
