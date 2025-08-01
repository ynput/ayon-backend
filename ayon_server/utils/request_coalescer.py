import asyncio
import hashlib
from collections.abc import Callable, Coroutine
from typing import Any, Generic, TypeVar


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


T = TypeVar("T")


class RequestCoalescer(Generic[T]):
    _instance: "RequestCoalescer[Any] | None" = None
    lock: asyncio.Lock
    current_futures: dict[str, asyncio.Task[T]]
    current_waiters: dict[str, int]
    max_waiters: int = 20

    def __new__(cls) -> "RequestCoalescer[Any]":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.current_futures = {}
            cls._instance.current_waiters = {}
            cls._instance.lock = asyncio.Lock()
        return cls._instance

    async def __call__(
        self, func: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any
    ) -> T:
        base_key = _hash_args(func, args, kwargs)
        async with self.lock:
            waiters = self.current_waiters.get(base_key, 0)

            if base_key not in self.current_futures:
                # First request: store under base_key
                self.current_futures[base_key] = asyncio.create_task(
                    func(*args, **kwargs)
                )
                self.current_waiters[base_key] = 1
                selected_key = base_key

            elif waiters >= self.max_waiters:
                # Too many waiters: create a unique task
                unique_key = f"{base_key}:{waiters}"
                self.current_futures[unique_key] = asyncio.create_task(
                    func(*args, **kwargs)
                )
                self.current_waiters[unique_key] = 1
                selected_key = unique_key

            else:
                # Join existing task under base_key
                self.current_waiters[base_key] += 1
                selected_key = base_key

        try:
            return await self.current_futures[selected_key]
        finally:
            async with self.lock:
                if selected_key in self.current_waiters:
                    self.current_waiters[selected_key] -= 1
                    if self.current_waiters[selected_key] == 0:
                        self.current_futures.pop(selected_key, None)
                        self.current_waiters.pop(selected_key, None)
