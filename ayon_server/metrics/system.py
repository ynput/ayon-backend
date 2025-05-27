import time
from typing import Any

import aiocache
import psutil

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel


class Metric:
    key: str
    tags: dict[str, str] | None = None
    value: float

    def __init__(self, key: str, value: float, tags: dict[str, str] | None = None):
        self.key = key
        self.value = value
        if tags is not None:
            self.tags = tags
        else:
            self.tags = {}

    def render_prometheus(self, prefix: str = "ayon") -> str:
        if not self.tags:
            return f"{prefix}_{self.key} {self.value}\n"
        tags = ",".join([f'{k}="{v}"' for k, v in self.tags.items()])
        return f"{prefix}_{self.key}{{{tags}}} {self.value}\n"


class SystemMetricsData(OPModel):
    cpu_usage: float = Field(0, title="CPU usage", example=12.3)
    memory_usage: float = Field(0, title="Memory usage", example=12.3)
    swap_usage: float = Field(0, title="Swap usage", example=12.3)
    uptime_seconds: float = Field(0, title="Uptime", example=123456)
    runtime_seconds: float = Field(0, title="Runtime", example=123456)
    db_size_shared: int = Field(0, title="Shared database size", example=123456)
    db_size_total: int = Field(0, title="Total database size", example=123456)
    db_available_connections: int = Field(
        0,
        title="Available database connections",
        example=123456,
    )
    redis_size_total: int = Field(0, title="Total redis size", example=123456)
    storage_utilization_total: int = Field(
        0,
        title="Total storage utilization",
        example=123456,
    )


class SystemMetrics:
    def __init__(self):
        self.boot_time = psutil.boot_time()
        self.run_time = time.time()

    @aiocache.cached(ttl=120)
    async def get_db_sizes(self) -> list[Metric]:
        result = []
        query = """
            SELECT
                projects.name AS project_name,
                nspname AS schema_name,
                SUM(pg_total_relation_size(pg_class.oid)) AS schema_size
            FROM
                public.projects
            RIGHT JOIN pg_namespace
                ON pg_namespace.nspname ILIKE 'project_' || projects.name
            LEFT JOIN pg_class ON pg_class.relnamespace = pg_namespace.oid
            WHERE pg_namespace.nspname NOT IN ('pg_catalog', 'information_schema')
            GROUP BY projects.name, nspname
            ORDER BY projects.name;
        """
        res = await Postgres.fetch(query)
        total_size = 0
        for record in res:
            if project_name := record["project_name"]:
                tags = {"project": project_name}
                key = "db_size_project"
            elif record["schema_name"] == "public":
                tags = None
                key = "db_size_shared"
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

        redis_size = await Redis.get_total_size()

        return [
            Metric("cpu_usage", psutil.cpu_percent()),
            Metric("memory_usage", mem_usage),
            Metric("swap_usage", psutil.swap_memory().percent),
            Metric("uptime_seconds", time.time() - self.boot_time),
            Metric("runtime_seconds", time.time() - self.run_time),
            Metric("redis_size_total", redis_size),
        ]

    async def render_prometheus(self) -> str:
        result = ""
        for metric in await self.status():
            result += metric.render_prometheus()

        for metric in await self.get_upload_sizes():
            result += metric.render_prometheus()

        for metric in await self.get_db_sizes():
            result += metric.render_prometheus()

        # ~realtime data
        db_avail = Metric(
            "db_available_connections", Postgres.get_available_connections()
        )
        result += db_avail.render_prometheus()

        return result

    @aiocache.cached(ttl=120)
    async def get_upload_sizes(self) -> list[Metric]:
        result: list[Metric] = []

        q = "SELECT name FROM public.projects ORDER BY name"
        projects = await Postgres.fetch(q)
        project_names = [row["name"] for row in projects]
        total_size = 0

        for project_name in project_names:
            # Uploads size
            res = await Postgres.fetch(
                f"SELECT SUM(size) FROM project_{project_name}.files"
            )
            uploads_size = res[0]["sum"] or 0
            total_size += uploads_size

            project_size = uploads_size

            # Thumbnails size (originals)
            # if the originalSize is null, thumbnail is from ayon <1.5.0
            # if the originalSize is equal to thumbnailSize,
            # thumbnail wasn't scaled down and it is only stored in
            # the database and origianal wasn't stored in the storage

            res = await Postgres.fetch(
                f"""
                SELECT SUM((meta->'originalSize')::BIGINT)
                FROM project_{project_name}.thumbnails
                WHERE meta->'originalSize' IS NOT NULL  -- Ayon <1.5.0
                AND meta->'originalSize' != meta->'thumbnailSize'
                """
            )

            thumbnails_size = res[0]["sum"] or 0
            project_size += thumbnails_size

            m = Metric(
                "storage_utilization_project",
                project_size,
                {"project": project_name},
            )
            result.append(m)

        result.append(Metric("storage_utilization_total", total_size))
        return result

    async def get_system_metrics_data(
        self,
        saturated: bool = False,
    ) -> SystemMetricsData | None:
        """System metrics data
        Contains information about machine utilization,
        and database sizes.
        """
        result: dict[str, Any] = {}
        for metric in await self.status():
            result[metric.key] = metric.value

        for metric in await self.get_db_sizes():
            if metric.key in ["db_size_total", "db_size_shared"]:
                result[metric.key] = metric.value

        for metric in await self.get_upload_sizes():
            if metric.key == "storage_utilization_total":
                result[metric.key] = metric.value

        return SystemMetricsData(**result)


system_metrics = SystemMetrics()
