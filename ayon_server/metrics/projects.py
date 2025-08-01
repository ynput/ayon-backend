from typing import Any

from ayon_server.entities import ProjectEntity
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .system import system_metrics

SATURATED_ONLY = "Collected only in the 'saturated' mode."


class ProjectCounts(OPModel):
    total: int = Field(0, title="Total projects", example=6)
    active: int = Field(0, title="Active projects", example=1)


class ProjectMetrics(OPModel):
    """Project metrics model"""

    nickname: str = Field(..., title="Project nickname", example="crazy-pink-cat")

    folder_count: int = Field(0, title="Folder count", example=52)
    product_count: int = Field(0, title="Product count", example=587)
    version_count: int = Field(0, title="Version count", example=2348)
    representation_count: int = Field(0, title="Representation count", example=2888)
    task_count: int = Field(0, title="Task count", example=222)
    workfile_count: int = Field(0, title="Workfile count", example=323)
    root_count: int | None = Field(None, title="Root count", example=2)
    team_count: int | None = Field(None, title="Team count", example=2)
    duration: int | None = Field(
        None,
        title="Duration",
        description="Duration in days",
        example=30,
    )

    db_size: int | None = Field(None)
    storage_utilization: int | None = Field(None)

    # Saturated metrics

    folder_types: list[str] | None = Field(
        None,
        title="Folder types",
        description=f"List of folder types in the project. {SATURATED_ONLY}",
        example=["Folder", "Asset", "Episode", "Sequence"],
    )
    task_types: list[str] | None = Field(
        None,
        title="Task types",
        description=f"List of task types in the project. {SATURATED_ONLY}",
        example=["Art", "Modeling", "Texture", "Lookdev"],
    )
    statuses: list[str] | None = Field(
        None,
        title="Statuses",
        description=f"List of statuses in the project. {SATURATED_ONLY}",
        example=["Not ready", "In progress", "Pending review", "Approved"],
    )


async def get_project_counts(
    saturated: bool = False,
    system: bool = False,
) -> ProjectCounts | None:
    """Number of total and active projects"""
    query = """
    SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE active) AS active
    FROM public.projects;
    """

    async for row in Postgres.iterate(query):
        return ProjectCounts(
            total=row["total"] or 0,
            active=row["active"] or 0,
        )
    return None


async def get_project_metrics(
    project: ProjectEntity,
    saturated: bool = False,
    system: bool = False,
) -> ProjectMetrics:
    result: dict[str, Any] = {
        "nickname": project.nickname,
    }

    for entity_type in [
        "folder",
        "product",
        "version",
        "representation",
        "task",
        "workfile",
    ]:
        query = f"""
        SELECT COUNT(*) AS c
        FROM project_{project.name}.{entity_type}s
        """

        try:
            res = await Postgres.fetch(query)
        except Exception:
            continue
        result[f"{entity_type}_count"] = res[0]["c"]

    if roots := project.config.get("roots", {}):
        result["root_count"] = len(roots)

    if teams := project.data.get("teams", []):
        result["team_count"] = len(teams)

    start_date = project.attrib.startDate
    end_date = project.attrib.endDate
    if start_date and end_date:
        result["duration"] = (end_date - start_date).days

    if system:
        db_sizes = await system_metrics.get_db_sizes()
        db_size = next(
            (
                m.value
                for m in db_sizes
                if m.tags.get("project", "").lower() == project.name.lower()
            ),
            None,
        )
        result["db_size"] = db_size or 0  # 0 should never happen

        storage_utilizations = await system_metrics.get_upload_sizes()
        storage_utilization = next(
            (
                m.value
                for m in storage_utilizations
                if m.tags.get("project", "").lower() == project.name.lower()
            ),
            None,
        )
        result["storage_utilization"] = storage_utilization or 0

    if saturated:
        result["folder_types"] = [f["name"] for f in project.folder_types]
        result["task_types"] = [t["name"] for t in project.task_types]
        result["statuses"] = [s["name"] for s in project.statuses]

    return ProjectMetrics(**result)


async def get_projects(
    saturated: bool = False, system: bool = False
) -> list[ProjectMetrics] | None:
    """Project specific metrics

    Contain information about size and usage of each active project.
    """
    projects = await get_project_list()

    res = []
    for project_item in projects:
        if not project_item.active:
            continue
        if project_item.role in ["demo", "test"]:
            continue
        project = await ProjectEntity.load(project_item.name)
        metrics = await get_project_metrics(
            project=project,
            saturated=saturated,
            system=system,
        )
        res.append(metrics)
    return res


async def get_average_project_event_count(
    saturated: bool = False, system: bool = False
) -> int | None:
    """Average number of events per project

    This disregards projects with less than 300 events
    (such as testing projects).
    """

    query = """
        SELECT AVG(event_count) AS average_event_count_per_project
        FROM (
            SELECT project_name, COUNT(*) AS event_count
            FROM public.events
            GROUP BY project_name
            HAVING COUNT(*) >= 300 and project_name is not null
        ) AS subquery;
    """

    async for row in Postgres.iterate(query):
        res = row["average_event_count_per_project"]
        if not res:
            return None
        return int(res)
    return None
