import inspect
import json
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

from pydantic import BaseModel
from redis import asyncio as aioredis
from redis.asyncio.client import PubSub

from ayon_server.config import ayonconfig
from ayon_server.logging import logger
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

T = TypeVar("T", bound=Callable[..., Coroutine[Any, Any, Any]])


def _make_cache_key(
    func: Callable[..., Any],
    ns: str,
    key_template: str,
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> str:
    """
    Generates the full Redis key from the namespace, key template,
    and function arguments.
    """
    try:
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        format_args = {
            k: v
            for i, (k, v) in enumerate(bound_args.arguments.items())
            if i > 0 or k != "self"  # Exclude the 'self' argument from key generation
        }

        key = key_template.format(**format_args)

    except Exception as e:
        logger.warning(
            f"Could not format cache key for {func.__name__}. "
            f"Falling back to default key generation. Error: {e}"
        )

        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        skip_first = False
        if args and params:
            first_param = params[0]
            if (
                first_param is not None
                and first_param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            ):
                skip_first = True

        relevant_args = args[1:] if skip_first else args
        arg_str = "_".join(str(a) for a in relevant_args)

        kwarg_str = "_".join(f"{k}_{v}" for k, v in kwargs.items())
        key = f"{func.__name__}_{arg_str}_{kwarg_str}"

    return f"{ns}:{key}"


class Redis:
    connected: bool = False
    redis_pool: aioredis.Redis
    prefix: str = ""

    @classmethod
    async def connect(cls) -> None:
        """Create a Redis connection pool"""
        cls.redis_pool = aioredis.from_url(ayonconfig.redis_url)

        try:
            t = cls.redis_pool.ping()
            if isinstance(t, Awaitable):
                res = await t
            else:
                res = t
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

    @classmethod
    def cached(
        cls,
        ns: str,
        key: str,
        ttl: int = 60 * 5,
        model: type[BaseModel] | None = None,
    ) -> Callable[[T], T]:
        """
        Decorator to cache the result of an async function in Redis.
        The function must return a JSON-serializable object.
        """

        def decorator(func: T) -> T:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
                full_key = _make_cache_key(func, ns, key, *args, **kwargs)

                cached_result = await cls.get_json(ns, full_key.removeprefix(f"{ns}:"))

                if cached_result is not None:
                    logger.trace(f"Cache hit for key: {full_key}")
                    if model is not None:
                        try:
                            return model(**cached_result)
                        except (TypeError, json.JSONDecodeError) as e:
                            logger.error(
                                f"Failed to parse cached result for {full_key}: {e}"
                            )
                            # Fall through to recompute the value
                    return cached_result

                logger.trace(f"Cache miss for key: {full_key}")
                result = await func(*args, **kwargs)

                if result is not None:
                    try:
                        await cls.set_json(
                            ns,
                            full_key.removeprefix(f"{ns}:"),
                            result,
                            ttl=ttl,
                        )
                    except (TypeError, json.JSONDecodeError, ConnectionError) as e:
                        logger.warning(f"Failed to set cache for {full_key}: {e}")

                return result

            return wrapper  # type: ignore[return-value]

        return decorator
