import time

from ayon_server.info import ReleaseInfo, get_release_info, get_uptime, get_version
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .projects import ProjectCounts, ProjectMetrics, get_project_counts, get_projects
from .settings import SettingsOverrides, get_studio_settings_overrides
from .users import UserCounts, get_user_counts


async def get_average_project_event_count(saturated: bool) -> int:
    """Average number of events per project

    This disregards projects with less than 300 events
    (such as testing projects).
    """

    query = """
        SELECT AVG(event_count) AS average_event_count_per_project
        FROM (
            SELECT project_name, COUNT(*) AS event_count
            FROM events
            GROUP BY project_name
            HAVING COUNT(*) >= 300 and project_name is not null
        ) AS subquery;
    """

    async for row in Postgres.iterate(query):
        res = row["average_event_count_per_project"]
        if not res:
            return 0
        return int(res)


class ProductionBundle(OPModel):
    addons: dict[str, str] = Field(
        default_factory=dict,
        title="Addons",
        description="Addons and their versions used in the production bundle",
    )
    launcher_version: str = Field(..., title="Launcher version")


class Metrics(OPModel):
    """Metrics model"""

    version: str = Field(default_factory=get_version, title="Ayon version")

    release_info: ReleaseInfo | None = Field(
        default_factory=get_release_info,
        title="Release info",
        description="Information about the exact branch and commit of the current release",
    )

    uptime: float = Field(
        default_factory=get_uptime,
        title="Uptime",
        description="Time (seconds) since the server was started",
    )

    user_counts: UserCounts | None = Field(
        None,
        title="User counts",
    )

    project_counts: ProjectCounts | None = Field(
        None,
        title="Project counts",
    )

    projects: list[ProjectMetrics] | None = Field(None, title="List of projects")

    average_project_event_count: int = Field(
        None,
        title="Average project event count",
        description=get_average_project_event_count.__doc__,
    )

    installed_addons: list[tuple[str, str]] = Field(default_factory=list)

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
