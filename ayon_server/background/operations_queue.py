import asyncio
from typing import NamedTuple

from ayon_server.background.background_worker import BackgroundWorker
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.operations.project_level import (
    OperationsProgress,
    ProjectLevelOperations,
)

BACKGROUND_OPS_TTL = 1800  # 30 minutes


class QueuedOperations(NamedTuple):
    task_id: str
    ops: ProjectLevelOperations
    can_fail: bool


async def _execute_background_operations(
    task_id: str,
    ops: ProjectLevelOperations,
    *,
    can_fail: bool,
) -> None:
    await Redis.set_json(
        "background-operations",
        task_id,
        {
            "status": "in_progress",
            "progress": 0.0,
        },
        ttl=BACKGROUND_OPS_TTL,
    )

    async def handle_progress(progress: OperationsProgress) -> None:
        percent = ((progress.index / progress.total) if progress.total else 0.0) * 100.0
        try:
            await Redis.set_json(
                "background-operations",
                task_id,
                {
                    "status": "in_progress",
                    "progress": percent,
                },
                ttl=BACKGROUND_OPS_TTL,
            )
        except Exception:
            pass  # not super important

    response = await ops.process(
        can_fail=can_fail,
        raise_on_error=False,
        wait_for_events=True,
        progress_handler=handle_progress,
    )

    # TODO: To be discussed.
    # should we use failed? probably not, because the task itself completed
    # and the result is available. depending on can_fail,
    # the result may contain errors, but the task itself is completed.
    # status = "completed" if response.success else "failed"

    await Redis.set_json(
        "background-operations",
        task_id,
        {
            "status": "completed",
            "result": response.dict(),
            "progress": 100.0,
        },
        ttl=BACKGROUND_OPS_TTL,
    )


class OperationsQueue(BackgroundWorker):
    """Serializes background project operations within a single replica.

    Background operations (POST .../operations/background) used to be fired
    off as unmanaged fastapi BackgroundTasks - one per request, with no limit
    on how many could run at once. That allowed concurrent requests to clash
    on the same project (e.g. piling up materialized view refreshes) and let
    a burst of requests overload a single replica.

    This worker processes queued operations one at a time, per replica.
    It does not coordinate across replicas.
    """

    def initialize(self):
        self.queue: asyncio.Queue[QueuedOperations] = asyncio.Queue()

    async def enqueue(
        self,
        task_id: str,
        ops: ProjectLevelOperations,
        *,
        can_fail: bool,
    ) -> None:
        req_count = await Redis.incr(
            "global",
            "concurrent-background-operations",
            ttl=BACKGROUND_OPS_TTL,
        )
        msg = "Queueing background operations"
        if req_count > 2:
            msg += f" ({req_count - 1} already queued or running)"
            logger.debug(msg)
        else:
            logger.trace(msg)

        await self.queue.put(QueuedOperations(task_id, ops, can_fail))

    async def run(self):
        while True:
            task_id, ops, can_fail = await self.queue.get()
            try:
                await _execute_background_operations(task_id, ops, can_fail=can_fail)
            except Exception:
                log_traceback(f"Background operations task {task_id} failed")
            finally:
                self.queue.task_done()
                await Redis.decr("global", "concurrent-background-operations")


operations_queue = OperationsQueue()
