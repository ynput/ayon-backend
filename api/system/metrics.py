import tracemalloc

from fastapi import Query
from fastapi.responses import PlainTextResponse

from ayon_server.api.dependencies import (
    ApiKey,
    CurrentUser,
    CurrentUserOptional,
    NoTraces,
)
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.metrics import Metrics, get_metrics
from ayon_server.metrics.system import system_metrics

from .router import router


@router.get("/metrics", response_model_exclude_none=True)
async def get_production_metrics(
    user: CurrentUser,
    system: bool = Query(
        False,
        description="Collect system metrics",
    ),
    saturated: bool = Query(
        False,
        description="Collect saturated (more granular) metrics",
    ),
) -> Metrics:
    """Get production related metrics"""

    if not user.is_admin:
        raise ForbiddenException("Access denied")

    metrics = await get_metrics(saturated=saturated, system=system, force=True)
    return metrics


@router.get("/metrics/system", dependencies=[NoTraces])
async def get_system_metrics(
    user: CurrentUserOptional,
    api_key: ApiKey,
) -> PlainTextResponse:
    """Get system metrics in Prometheus format"""

    result = ""

    if user is not None and not user.is_admin:
        user = None

    if user is None:
        if api_key is None:
            raise ForbiddenException("Access denied")
        if api_key != ayonconfig.metrics_api_key:
            raise ForbiddenException("Access denied")

    # Get user requests count

    try:
        concurrent_requests = int(await Redis.get("concurrent-requests", "total"))
    except Exception:
        concurrent_requests = 0

    result += f"ayon_concurrent_requests_total {concurrent_requests}\n"

    async for record in Postgres.iterate("SELECT name FROM users"):
        name = record["name"]
        requests = await Redis.get("user-requests", name)
        num_requests = 0 if requests is None else int(requests)
        if num_requests > 0:
            result += f'ayon_user_requests{{name="{name}"}} {num_requests}\n'

    # Get system metrics
    result += await system_metrics.render_prometheus()

    return PlainTextResponse(result)


#
# Tracemalloc metrics
#

snapshot: tracemalloc.Snapshot | None = None


@router.get("/metrics/tracemalloc", dependencies=[NoTraces])
async def get_tracemalloc_metrics(
    user: CurrentUserOptional,
    api_key: ApiKey,
) -> PlainTextResponse:
    """Get tracemalloc metrics in Prometheus format"""

    result = ""

    if user is not None and not user.is_admin:
        user = None

    if user is None:
        if api_key is None:
            raise ForbiddenException("Access denied")
        if api_key != ayonconfig.metrics_api_key:
            raise ForbiddenException("Access denied")

    global snapshot
    if snapshot is None or not tracemalloc.is_tracing():
        tracemalloc.start()
        snapshot = tracemalloc.take_snapshot()
    current_snapshot = tracemalloc.take_snapshot()
    top_stats = current_snapshot.compare_to(snapshot, "lineno")

    result += "# Tracemalloc metrics\n"
    for stat in top_stats[:10]:
        tb0 = stat.traceback[0]
        filename = (
            tb0.filename.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
        )
        result += f'ayon_tracemalloc_size_diff_bytes{{file="{filename}", line="{tb0.lineno}"}} {stat.size_diff}\n'  # noqa: E501
    return PlainTextResponse(result)


@router.delete("/metrics/tracemalloc", dependencies=[NoTraces])
async def stop_tracemalloc_metrics(
    user: CurrentUserOptional,
    api_key: ApiKey,
) -> PlainTextResponse:
    """Stop tracemalloc metrics collection"""

    if user is not None and not user.is_admin:
        user = None

    if user is None:
        if api_key is None:
            raise ForbiddenException("Access denied")
        if api_key != ayonconfig.metrics_api_key:
            raise ForbiddenException("Access denied")

    global snapshot
    snapshot = None
    tracemalloc.stop()

    return PlainTextResponse("Tracemalloc metrics collection stopped")
