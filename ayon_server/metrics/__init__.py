import time

from ayon_server.info import ReleaseInfo, get_release_info, get_uptime, get_version
from ayon_server.types import Field, OPModel

from .bundles import (
    ProductionBundle,
    get_installed_addons,
    get_production_bundle,
)
from .projects import (
    ProjectCounts,
    ProjectMetrics,
    get_average_project_event_count,
    get_project_counts,
    get_projects,
)
from .services import ServiceInfo, get_active_services
from .settings import SettingsOverrides, get_studio_settings_overrides
from .users import UserCounts, get_user_counts


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
]


async def get_metrics(saturated: bool = False) -> Metrics:
    """Get metrics"""

    for metric in METRICS_SETUP:
        name = metric["name"]
        getter = metric["getter"]
        ttl_h = metric.get("ttl", 24)

        assert isinstance(ttl_h, int), f"ttl must be an integer, got {ttl_h}"
        assert isinstance(name, str), f"name must be a string, got {name}"
        assert callable(getter), f"getter must be callable, got {getter}"
        ttl = ttl_h * 60 * 60

        if name not in METRICS_SNAPSHOT:
            value = await getter(saturated=saturated)
            METRICS_SNAPSHOT[name] = {
                "value": value,
                "timestamp": time.time(),
            }
        else:
            snapshot = METRICS_SNAPSHOT[name]
            if time.time() - snapshot["timestamp"] > ttl:
                value = await getter(saturated=saturated)
                METRICS_SNAPSHOT[name] = {
                    "value": value,
                    "timestamp": time.time(),
                }

    return Metrics(**{key: value["value"] for key, value in METRICS_SNAPSHOT.items()})
