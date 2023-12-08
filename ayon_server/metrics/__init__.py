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
        description="Information about the exact branch and commit of the current release",
        example=get_release_info(),
    )

    uptime: float = Field(
        default_factory=get_uptime,
        title="Uptime",
        description="Time (seconds) since the server was started",
        example=get_uptime(),
    )

    user_counts: UserCounts | None = Field(
        None,
        title="User counts",
    )

    project_counts: ProjectCounts | None = Field(
        None,
        title="Project counts",
    )

    projects: list[ProjectMetrics] | None = Field(None, title="Project statistics")

    average_project_event_count: int = Field(
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

    studio_settings_overrides: list[SettingsOverrides] | None = Field(None)


METRICS_SNAPSHOT = {}
METRICS_SETUP = [
    {
        "name": "project_counts",
        "getter": get_project_counts,
        "ttl": 60,
    },
    {
        "name": "user_counts",
        "getter": get_user_counts,
        "ttl": 60,
    },
    {
        "name": "average_project_event_count",
        "getter": get_average_project_event_count,
        "ttl": 60,
    },
    {
        "name": "projects",
        "getter": get_projects,
        "ttl": 60,
    },
    {
        "name": "studio_settings_overrides",
        "getter": get_studio_settings_overrides,
        "ttl": 60,
    },
    {
        "name": "production_bundle",
        "getter": get_production_bundle,
        "ttl": 60,
    },
    {
        "name": "installed_addons",
        "getter": get_installed_addons,
        "ttl": 60,
    },
]


async def get_metrics(saturated: bool = True) -> Metrics:
    """Get metrics"""

    for metric in METRICS_SETUP:
        name = metric["name"]
        getter = metric["getter"]
        ttl = metric["ttl"]

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
