import time

import aiocache
import psutil
from fastapi import Query
from fastapi.responses import PlainTextResponse

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.metrics import Metrics, get_metrics

from .router import router


class Metric:
    key: str
    tags: dict[str, str] | None = None
    value: float

    def __init__(self, key: str, value: float, tags: dict[str, str] | None = None):
        self.key = key
        self.value = value
        if tags is not None:
            self.tags = tags

    def render(self, prefix: str = "ayon") -> str:
        if self.tags is None:
            return f"{prefix}_{self.key} {self.value}"
        tags = ",".join([f'{k}="{v}"' for k, v in self.tags.items()])
        return f"{prefix}_{self.key}{{{tags}}} {self.value}"


class SystemMetrics:
    def __init__(self):
        self.boot_time = psutil.boot_time()
        self.run_time = time.time()

    @aiocache.cached(ttl=60)
    async def get_db_sizes(self) -> list[Metric]:
        result = []
        query = """
            SELECT
                nspname AS schema_name,
                SUM(pg_total_relation_size(pg_class.oid)) AS schema_size
            FROM pg_class
            JOIN pg_namespace ON pg_class.relnamespace = pg_namespace.oid
            WHERE pg_namespace.nspname NOT IN ('pg_catalog', 'information_schema')
            GROUP BY nspname
        """
        res = await Postgres.fetch(query)
        total_size = 0
        for record in res:
            schema = record["schema_name"]
            if schema == "public":
                tags = None
                key = "db_size_shared"
            elif schema.startswith("project_"):
                tags = {"project": schema[8:]}
                key = "db_size_project"
            else:
                continue
            result.append(Metric(key, record["schema_size"], tags))
            total_size += record["schema_size"]
        result.append(Metric("db_size_total", total_size))
        return result

    @aiocache.cached(ttl=5)
    async def status(self) -> list[Metric]:
        mem = psutil.virtual_memory()
        mem_usage = 100 * ((mem.total - mem.available) / mem.total)

        return [
            Metric("cpu_usage", psutil.cpu_percent()),
            Metric("memory_usage", mem_usage),
            Metric("swap_usage", psutil.swap_memory().percent),
            Metric("uptime_seconds", time.time() - self.boot_time),
            Metric("runtime_seconds", time.time() - self.run_time),
        ]


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

    for metric in await system_metrics.status():
        result += metric.render() + "\n"

    for metric in await system_metrics.get_db_sizes():
        result += metric.render() + "\n"

    return PlainTextResponse(result)
