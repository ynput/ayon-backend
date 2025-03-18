from collections.abc import Awaitable
from typing import Any

from redis import asyncio as aioredis
from redis.asyncio.client import PubSub

from ayon_server.config import ayonconfig
from ayon_server.utils import json_dumps, json_loads

GET_SIZE_SCRIPT = """
local cursor = "0"
local total_size = 0
local key_pattern = ARGV[1]

repeat
    local result = redis.call("SCAN", cursor, "MATCH", key_pattern, "COUNT", 1000)
    cursor = result[1]
    local keys = result[2]

    for i, key in ipairs(keys) do
        total_size = total_size + redis.call("MEMORY", "USAGE", key)
    end
until cursor == "0"

return total_size
"""


class Redis:
    connected: bool = False
    redis_pool: aioredis.Redis
    prefix: str = ""

    @classmethod
    async def connect(cls) -> None:
        """Create a Redis connection pool"""
        cls.redis_pool = aioredis.from_url(ayonconfig.redis_url)

        try:
            res = await cls.redis_pool.ping()
            if not res:
                raise ConnectionError("Failed to connect to Redis")
        except Exception as e:
            raise ConnectionError("Failed to connect to Redis") from e

        cls.connected = True
        cls.prefix = (
            f"{ayonconfig.redis_key_prefix}-" if ayonconfig.redis_key_prefix else ""
        )

    @classmethod
    async def get(cls, namespace: str, key: str) -> Any:
        """Get a value from Redis"""
        if not cls.connected:
            await cls.connect()
        value = await cls.redis_pool.get(f"{cls.prefix}{namespace}-{key}")
        return value

    @classmethod
    async def get_json(cls, namespace: str, key: str) -> Any:
        """Get a JSON-serialized value from Redis"""
        if not cls.connected:
            await cls.connect()
        value = await cls.get(namespace, key)
        if value is None:
            return None
        try:
            return json_loads(value)
        except Exception as e:
            raise ValueError(f"Invalid JSON in {namespace}-{key}") from e

    @classmethod
    async def set(
        cls, namespace: str, key: str, value: str | bytes, ttl: int = 0
    ) -> None:
        """Create/update a record in Redis

        Optional ttl argument may be provided to set expiration time.
        """
        if not cls.connected:
            await cls.connect()
        command = ["set", f"{cls.prefix}{namespace}-{key}", value]
        if ttl:
            command.extend(["ex", str(ttl)])

        await cls.redis_pool.execute_command(*command)

    @classmethod
    async def set_json(cls, namespace: str, key: str, value: Any, ttl: int = 0) -> None:
        """Create/update a record in Redis with JSON-serialized value"""
        payload = json_dumps(value)
        await cls.set(namespace, key, payload, ttl)

    @classmethod
    async def delete(cls, namespace: str, key: str) -> None:
        """Delete a record from Redis"""
        if not cls.connected:
            await cls.connect()
        await cls.redis_pool.delete(f"{cls.prefix}{namespace}-{key}")

    @classmethod
    async def incr(cls, namespace: str, key: str) -> int:
        """Increment a value in Redis"""
        if not cls.connected:
            await cls.connect()
        res = await cls.redis_pool.incr(f"{cls.prefix}{namespace}-{key}")
        return res

    @classmethod
    async def expire(cls, namespace: str, key: str, ttl: int) -> None:
        """Set a TTL for a key in Redis"""
        if not cls.connected:
            await cls.connect()
        await cls.redis_pool.expire(f"{cls.prefix}{namespace}-{key}", ttl)

    @classmethod
    async def pubsub(cls) -> PubSub:
        """Create a Redis pubsub connection"""
        if not cls.connected:
            await cls.connect()
        return cls.redis_pool.pubsub()

    @classmethod
    async def publish(cls, message: str, channel: str | None = None) -> None:
        """Publish a message to a Redis channel"""
        if not cls.connected:
            await cls.connect()
        if channel is None:
            channel = ayonconfig.redis_channel
        await cls.redis_pool.publish(channel, message)

    @classmethod
    async def keys(cls, namespace: str) -> list[str]:
        if not cls.connected:
            await cls.connect()
        keys = await cls.redis_pool.keys(f"{cls.prefix}{namespace}-*")
        return [
            key.decode("ascii").removeprefix(f"{cls.prefix}{namespace}-")
            for key in keys
        ]

    @classmethod
    async def delete_ns(cls, namespace: str):
        if not cls.connected:
            await cls.connect()
        keys = await cls.redis_pool.keys(f"{cls.prefix}{namespace}-*")
        for key in keys:
            await cls.redis_pool.delete(key)

    @classmethod
    async def iterate(cls, namespace: str):
        """Iterate over stored keys and yield [key, payload] tuples
        matching given namespace.
        """
        if not cls.connected:
            await cls.connect()

        async for key in cls.redis_pool.scan_iter(
            match=f"{cls.prefix}{namespace}-*", count=1000
        ):
            key_without_ns = key.decode("ascii").removeprefix(
                f"{cls.prefix}{namespace}-"
            )
            payload = await cls.redis_pool.get(key)
            yield key_without_ns, payload

    @classmethod
    async def get_total_size(cls) -> int:
        """Get total memory usage of all keys in with the current prefix"""

        if not cls.connected:
            await cls.connect()

        try:
            result: Awaitable[str] | str = cls.redis_pool.eval(
                GET_SIZE_SCRIPT, 0, f"{cls.prefix}*"
            )

            if isinstance(result, Awaitable):
                value = await result
            else:
                value = result
        except Exception:
            return 0

        if value is None:
            return 0
        return int(value)
