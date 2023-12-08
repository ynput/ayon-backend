from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class ProjectCounts(OPModel):
    total: int = Field(0, title="Total projects")
    active: int = Field(0, title="Active projects")


class ProjectMetrics(OPModel):
    """Project metrics model"""

    folder_count: int = Field(0, title="Folder count")
    product_count: int = Field(0, title="Product count")
    version_count: int = Field(0, title="Version count")
    representation_count: int = Field(0, title="Representation count")
    task_count: int = Field(0, title="Task count")
    workfile_count: int = Field(0, title="Workfile count")
    duration: int = Field(0, title="Duration", description="Duration in days")
    team_count: int = Field(0, title="Team count")

    # Saturated metrics

    folder_types: list[str] | None = Field(None, title="Folder types")
    task_types: list[str] | None = Field(None, title="Task types")
    statuses: list[str] | None = Field(None, title="Statuses")
    # Do not include tags (may be huge and sensitive)
    # tags: list[str] | None = Field(None, title="Tags")


async def get_project_counts(saturated: bool) -> ProjectCounts:
    query = """
    SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE active) AS active
    FROM projects;
    """

    async for row in Postgres.iterate(query):
        return ProjectCounts(
            total=row["total"] or 0,
            active=row["active"] or 0,
        )


async def get_project_metrics(project_name: str, saturated: bool) -> ProjectMetrics:

    data = {}
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
        FROM project_{project_name}.{entity_type}s
        """

        res = await Postgres.fetch(query)
        data[f"{entity_type}_count"] = res[0]["c"]

    if saturated:
        for entity_type in ["folder", "task"]:
            query = f"""
            SELECT DISTINCT ({entity_type}_type) as t
            FROM project_{project_name}.{entity_type}s
            """

            res = await Postgres.fetch(query)
            data[f"{entity_type}_types"] = [r["t"] for r in res]

    return ProjectMetrics(**data)


async def get_projects(saturated: bool) -> list[ProjectMetrics]:
    query = """
    SELECT name
    FROM projects
    WHERE active IS TRUE;
    """

    res = await Postgres.fetch(query)
    return [await get_project_metrics(r["name"], saturated) for r in res]


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
