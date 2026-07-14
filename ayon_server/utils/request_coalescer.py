import asyncio
import hashlib
from collections.abc import Callable, Coroutine
from typing import Any, Generic, TypeVar
from uuid import uuid4


def _hash_args(func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """
    Generates a hash from the function arguments and keyword arguments.

    This is probably a terrible idea.
    """
    if hasattr(func, "__func__") and hasattr(func, "__self__"):
        # Bound method (either instance or class method).
        # stable identifier since Python recreates bound method objects on access.
        self_class = (
            func.__self__
            if isinstance(func.__self__, type)
            else func.__self__.__class__
        )
        func_name = f"{self_class.__module__}.{self_class.__qualname__}.{func.__func__.__name__}"  # noqa: E501
        func_id = f"{func_name} (bound to {id(func.__self__)})"
    elif hasattr(func, "__qualname__"):
        func_id = f"{getattr(func, '__module__', '')}.{func.__qualname__}"
    else:
        func_id = f"{str(func)} (id: {id(func)})"

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
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        base_key = _hash_args(func, *args, **kwargs)
        async with self.lock:
            # Look for an existing task batch that has space for another waiter
            selected_key = None
            selected_future: asyncio.Task[T] | None = None
            for key in self.current_futures:
                if (
                    key == base_key or key.startswith(f"{base_key}:")
                ) and self.current_waiters.get(key, 0) < self.max_waiters:
                    selected_key = key
                    selected_future = self.current_futures[key]
                    break

            if selected_key is not None:
                self.current_waiters[selected_key] += 1
            else:
                if base_key not in self.current_futures:
                    selected_key = base_key
                else:
                    selected_key = f"{base_key}:{uuid4().hex}"

                self.current_futures[selected_key] = asyncio.create_task(
                    func(*args, **kwargs)
                )
                selected_future = self.current_futures[selected_key]
                self.current_waiters[selected_key] = 1

        try:
            assert selected_future is not None
            return await selected_future
        finally:
            async with self.lock:
                if selected_key in self.current_waiters:
                    self.current_waiters[selected_key] -= 1
                    if self.current_waiters[selected_key] == 0:
                        self.current_futures.pop(selected_key, None)
                        self.current_waiters.pop(selected_key, None)
