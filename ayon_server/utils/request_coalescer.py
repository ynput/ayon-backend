import asyncio
import hashlib
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar


def _hash_args(func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """
    Generates a hash from the function arguments and keyword arguments.

    This is probably a terrible idea.
    """
    func_id = str(id(func))
    arg_str = str(args)
    kwarg_str = str(sorted(kwargs.items()))
    combined_str = arg_str + kwarg_str + func_id
    return hashlib.md5(combined_str.encode()).hexdigest()


T = TypeVar("T", covariant=True)


class RequestCoalescer:
    _instance: "RequestCoalescer | None" = None
    lock: asyncio.Lock
    current_futures: dict[str, asyncio.Task[T]]

    def __new__(cls) -> "RequestCoalescer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.current_futures = {}
            cls._instance.lock = asyncio.Lock()
        return cls._instance

    async def __call__(
        self, func: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> T:
        key = _hash_args(func, args, kwargs)
        async with self.lock:
            if key not in self.current_futures:
                self.current_futures[key] = asyncio.create_task(func(*args, **kwargs))

        try:
            return await self.current_futures[key]
        finally:
            async with self.lock:
                self.current_futures.pop(key, None)
