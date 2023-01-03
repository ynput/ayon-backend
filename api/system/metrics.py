import time

import psutil
from fastapi import Depends
from fastapi.responses import PlainTextResponse

from ayon_server.api import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis

from .router import router


class SystemMetrics:
    def __init__(self):
        self.boot_time = psutil.boot_time()
        self.run_time = time.time()

    def status(self):
        mem = psutil.virtual_memory()
        mem_usage = 100 * ((mem.total - mem.available) / mem.total)
        return {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": mem_usage,
            "swap_usage": psutil.swap_memory().percent,
            "uptime_seconds": time.time() - self.boot_time,
            "runtime_seconds": time.time() - self.run_time,
        }


metrics = SystemMetrics()


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    tags=["System"],
)
async def get_system_metrics(
    user: UserEntity = Depends(dep_current_user),
):
    result = ""
    async for record in Postgres.iterate("SELECT name FROM users"):
        name = record["name"]
        requests = await Redis.get("user-requests", name)
        num_requests = 0 if requests is None else int(requests)
        result += f'ayon_user_requests{{name="{name}"}} {num_requests}\n'

    for k, v in metrics.status().items():
        result += f"ayon_{k} {v}\n"

    return PlainTextResponse(result)
