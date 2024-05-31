import time

import psutil
from fastapi import Query
from fastapi.responses import PlainTextResponse

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.metrics import Metrics, get_metrics

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


system_metrics = SystemMetrics()


#
# Endpoints
#


@router.get("/metrics", tags=["System"], response_model_exclude_none=True)
async def get_production_metrics(
    user: CurrentUser,
    saturated: bool = Query(
        False,
        description="Collect saturated (more granular) metrics",
    ),
) -> Metrics:
    """Get production related metrics"""

    metrics = await get_metrics(saturated=saturated)
    return metrics


@router.get("/metrics/system", tags=["System"])
async def get_system_metrics(user: CurrentUser) -> PlainTextResponse:
    """Get system metrics in Prometheus format"""

    result = ""

    # Get user requests count

    async for record in Postgres.iterate("SELECT name FROM users"):
        name = record["name"]
        requests = await Redis.get("user-requests", name)
        num_requests = 0 if requests is None else int(requests)
        if num_requests > 0:
            result += f'ayon_user_requests{{name="{name}"}} {num_requests}\n'

    # Get system metrics

    for k, v in system_metrics.status().items():
        result += f"ayon_{k} {v}\n"

    return PlainTextResponse(result)
