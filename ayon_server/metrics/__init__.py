__all__ = ["Metrics", "get_metrics"]

import time

import httpx

from ayon_server.config import ayonconfig
from ayon_server.constraints import Constraints
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.info import ReleaseInfo, get_release_info, get_uptime, get_version
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel

from .bundles import (
    ProductionBundle,
    get_installed_addons,
    get_production_bundle,
)
from .events import get_event_count_per_topic
from .projects import (
    ProjectCounts,
    ProjectMetrics,
    get_average_project_event_count,
    get_project_counts,
    get_projects,
)
from .services import ServiceInfo, get_active_services
from .settings import SettingsOverrides, get_studio_settings_overrides
from .system import SystemMetricsData, system_metrics
from .traffic import TrafficStat, get_traffic_stats
from .users import UserCounts, UserStat, get_user_counts, get_user_stats


def docfm(obj) -> str:
    """Format a docstring"""

    docstring = obj.__doc__
    lines = []
    for line in docstring.split("\n"):
        lines.append(line.strip())
    return "\n".join(lines)


class Metrics(OPModel):
    """Metrics model"""

    version: str = Field(
        default_factory=get_version,
        title="Ayon version",
        example=get_version(),
    )

    release_info: ReleaseInfo | None = Field(
        default_factory=get_release_info,
        title="Release info",
        description="Information about the branch and commit of the current release",
        example=get_release_info(),
    )

    uptime: float = Field(
        default_factory=get_uptime,
        title="Uptime",
        description="Time (seconds) since the server was (re)started",
        example=518163,
    )

    system: SystemMetricsData | None = Field(
        None,
        title="System metrics",
        description=docfm(system_metrics.get_system_metrics_data),
    )

    user_counts: UserCounts | None = Field(
        None,
        title="User counts",
        description=docfm(get_user_counts),
    )

    project_counts: ProjectCounts | None = Field(
        None,
        title="Project counts",
        example=1,
        description=docfm(get_project_counts),
    )

    projects: list[ProjectMetrics] | None = Field(
        None,
        title="Project statistics",
        description=docfm(get_projects),
    )

    average_project_event_count: int | None = Field(
        None,
        title="Average project event count",
        description=docfm(get_average_project_event_count),
    )

    installed_addons: list[tuple[str, str]] | None = Field(
        None,
        title="Installed addons",
        description=docfm(get_installed_addons),
        example=[
            ("maya", "1.0.0"),
            ("maya", "1.0.1"),
            ("ftrack", "1.2.3"),
        ],
    )

    event_topics: dict[str, int] | None = Field(
        None,
        title="Event topics count",
        description=(docfm(get_event_count_per_topic)),
    )

    production_bundle: ProductionBundle | None = Field(
        None,
        title="Production bundle",
        description=docfm(get_production_bundle),
    )

    studio_settings_overrides: list[SettingsOverrides] | None = Field(
        None,
        title="Studio settings overrides",
        description=docfm(get_studio_settings_overrides),
    )

    services: list[ServiceInfo] | None = Field(
        None,
        title="Services",
        description=docfm(get_active_services),
    )

    traffic_stats: list[TrafficStat] | None = Field(None, title="Traffic stats")
    user_stats: list[UserStat] | None = Field(None, title="User stats")


METRICS_SNAPSHOT = {}
METRICS_SETUP = [
    {
        "name": "project_counts",
        "getter": get_project_counts,
    },
    {
        "name": "user_counts",
        "getter": get_user_counts,
        "ttl": 50,
    },
    {
        "name": "average_project_event_count",
        "getter": get_average_project_event_count,
        "ttl": 50,
    },
    {
        "name": "projects",
        "getter": get_projects,
    },
    {
        "name": "studio_settings_overrides",
        "getter": get_studio_settings_overrides,
        "ttl": 30,
    },
    {
        "name": "production_bundle",
        "getter": get_production_bundle,
    },
    {
        "name": "installed_addons",
        "getter": get_installed_addons,
        "ttl": 24,
    },
    {
        "name": "active_services",
        "getter": get_active_services,
        "ttl": 10,
    },
    {
        "name": "event_topics",
        "getter": get_event_count_per_topic,
        "ttl": 10,
    },
    {
        "name": "traffic_stats",
        "getter": get_traffic_stats,
        "ttl": 24,
    },
    {
        "name": "user_stats",
        "getter": get_user_stats,
        "ttl": 24,
    },
]


async def get_metrics(
    saturated: bool = False, system: bool = False, force: bool = False
) -> Metrics:
    """Get metrics"""

    for metric in METRICS_SETUP:
        name = metric["name"]
        getter = metric["getter"]
        ttl_h = metric.get("ttl", 24)

        assert isinstance(ttl_h, int), f"ttl must be an integer, got {ttl_h}"
        assert isinstance(name, str), f"name must be a string, got {name}"
        assert callable(getter), f"getter must be callable, got {getter}"
        ttl = ttl_h * 60 * 60

        if name not in METRICS_SNAPSHOT or force:
            value = await getter(saturated=saturated, system=system)
            METRICS_SNAPSHOT[name] = {
                "value": value,
                "timestamp": time.time(),
            }
        else:
            snapshot = METRICS_SNAPSHOT[name]
            if time.time() - snapshot["timestamp"] > ttl:
                value = await getter(saturated=saturated, system=system)
                METRICS_SNAPSHOT[name] = {
                    "value": value,
                    "timestamp": time.time(),
                }
    if system:
        system_metrics_data = await system_metrics.get_system_metrics_data(
            saturated=saturated
        )
    else:
        system_metrics_data = None

    return Metrics(
        system=system_metrics_data,
        **{key: value["value"] for key, value in METRICS_SNAPSHOT.items()},
    )


async def should_post_metrics() -> bool:
    """Check if metrics should be posted to cloud API.

    Returns bool indicating if enough time (8 hours) has elapsed since last post,
    or if metrics have never been posted before.
    """
    last_collected = await Redis.get_json("global", "metrics-last-posted")
    if last_collected is None:
        return True
    if time.time() - last_collected > 8 * 3600:
        return True
    return False


async def post_metrics():
    try:
        headers = await CloudUtils.get_api_headers()
    except Exception:
        # if we can't get the headers, we can't send metrics
        return

    if not await should_post_metrics():
        return

    saturated = ayonconfig.metrics_send_saturated
    system = ayonconfig.metrics_send_system

    if not saturated:
        r = await Constraints.check("saturatedMetrics")
        if r:
            saturated = True
    if not system:
        r = await Constraints.check("systemMetrics")
        if r:
            system = True

    metrics = await get_metrics(saturated=saturated, system=system)
    payload = metrics.dict(exclude_none=True)

    try:
        async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
            await client.post(
                f"{ayonconfig.ynput_cloud_api_url}/api/v1/metrics",
                json=payload,
                headers=headers,
            )
    except Exception:
        # fail silently
        pass

    # update last posted timestamp
    # event if the post failed, we don't want to do unnecessary work
    # in the case the connection is down or so
    now = int(time.time())
    await Redis.set_json("global", "metrics-last-posted", now)
