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

    async for record in Postgres.iterate("SELECT name FROM users"):
        name = record["name"]
        requests = await Redis.get("user-requests", name)
        num_requests = 0 if requests is None else int(requests)
        if num_requests > 0:
            result += f'ayon_user_requests{{name="{name}"}} {num_requests}\n'

    # Get system metrics

    result += await system_metrics.render_prometheus()

    return PlainTextResponse(result)
