import asyncio
from collections.abc import Coroutine
from typing import Any

# The event loop keeps only weak references to tasks, so a task without
# a reference may be garbage collected before it finishes.
_background_tasks: set[asyncio.Task[Any]] = set()


def _on_task_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled() or task.exception() is None:
        return
    from ayon_server.logging import logger  # logging imports utils

    logger.opt(exception=task.exception()).error(
        f"Background task {task.get_name()} failed"
    )


def create_background_task(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None,
) -> asyncio.Task[Any]:
    """Run a coroutine in the background (fire and forget).

    Unlike `asyncio.create_task`, the task is kept until it finishes
    and its exception (if any) is logged.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task
