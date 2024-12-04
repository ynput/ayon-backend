import datetime
from typing import get_args

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.entities import ProjectEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .router import router


class EntityCounts(OPModel):
    folders: int = Field(..., description="Number of folders", example=10)
    products: int = Field(..., description="Number of products", example=98)
    versions: int = Field(..., description="Number of versions", example=512)
    representations: int = Field(
        ...,
        description="Number of representations",
        example=4853,
    )
    tasks: int = Field(..., description="Number of tasks", example=240)
    workfiles: int = Field(..., description="Number of workfiles", example=190)


@router.get("/entities")
async def get_project_entity_counts(
    user: CurrentUser, project_name: ProjectName
) -> EntityCounts:
    """Retrieve entity counts for a given project."""

    counts: dict[str, int] = {}
    for entity_type in get_args(ProjectLevelEntityType):
        res = await Postgres.fetch(
            f"""
            SELECT COUNT(id)
            FROM project_{project_name}.{entity_type}s
            """
        )
        counts[f"{entity_type}s"] = res[0][0]

    return EntityCounts(**counts)


#
# Project health
#


class HealthCompletion(OPModel):
    percentage: int = Field(
        ...,
        description="Percentage of tasks completed",
        example=69,
    )
    behind: int = Field(
        ...,
        description="Number of days tasks are not completed after due date",
        example=5,
    )
    ahead: int = Field(
        ...,
        description="Number of days tasks are completed before due date",
        example=3,
    )


class HealthStorageUsage(OPModel):
    quota: int = Field(..., description="Storage quota", example=1000000000)
    used: int = Field(..., description="Storage used", example=500000000)


class HealthTasks(OPModel):
    total: int = Field(..., description="Total number of tasks", example=100)
    completed: int = Field(..., description="Number of completed tasks", example=50)
    overdue: int = Field(..., description="Number of overdue tasks", example=10)


class Health(OPModel):
    completion: HealthCompletion = Field(..., description="Task completion")
    storage_usage: HealthStorageUsage = Field(..., description="Storage usage")
    tasks: HealthTasks = Field(..., description="Task statistics")
    statuses: dict[str, int] = Field(..., description="Task status statistics")


@router.get("/health")
async def get_project_health(
    user: CurrentUser,
    project_name: ProjectName,
) -> Health:
    project = await ProjectEntity.load(project_name)

    #
    # Statuses
    #

    completed_statuses = [
        p["name"] for p in project.statuses if p.get("state") == "done"
    ]
    now = datetime.datetime.now()

    total_tasks = 0
    completed_tasks = 0
    ahead = datetime.timedelta()
    behind = datetime.timedelta()
    late_tasks = 0
    statuses: dict[str, int] = {}

    query = f"SELECT status, attrib FROM project_{project_name}.tasks"
    async for row in Postgres.iterate(query):
        status = row["status"]
        attrib = row["attrib"]

        statuses[status] = statuses.get(status, 0) + 1

        try:
            end_date = datetime.datetime.fromisoformat(attrib.get("endDate"))
        except (TypeError, ValueError):
            end_date = None

        total_tasks += 1

        if status in completed_statuses:
            completed_tasks += 1

            if end_date and end_date > now:
                # Completed before due date
                ahead += end_date - now
            continue

        if end_date and end_date < now:
            # Overdue
            behind += now - end_date
            late_tasks += 1
            continue

    tasks = {
        "total": total_tasks,
        "completed": completed_tasks,
        "overdue": late_tasks,
    }

    #
    # Completion
    #

    percentage = ((completed_tasks / total_tasks) if total_tasks else 0) * 100
    completion = {
        "percentage": percentage,
        "behind": behind.days,
        "ahead": ahead.days,
    }

    #
    # Storage usage
    #

    # TODO
    storage_usage = {
        "quota": 20 * 1024 * 1024 * 1024,
        "used": 11 * 1024 * 1024 * 1024,
    }

    return Health(
        completion=HealthCompletion(**completion),
        storage_usage=HealthStorageUsage(**storage_usage),
        tasks=HealthTasks(**tasks),
        statuses=statuses,
    )


class ActivityResponseModel(OPModel):
    activity: list[int] = Field(
        ...,
        description="Activity per day normalized to 0-100",
        example=[0, 0, 0, 1, 12, 34, 32, 24, 25, 56, 18],
    )


def get_midnight_dates(number_of_days: int):
    today = datetime.datetime.now().date()
    dates = [today - datetime.timedelta(days=i) for i in range(number_of_days)]
    return [
        datetime.datetime.combine(date, datetime.datetime.min.time()) for date in dates
    ]


def normalize_list(numbers, threshold=100):
    max_value = max(numbers)
    if max_value > threshold:
        scale_factor = threshold / max_value
        return [int(value * scale_factor) for value in numbers]
    return numbers


@router.get("/activity")
async def get_project_activity(
    user: CurrentUser,
    project_name: ProjectName,
    days: int = Query(50, description="Number of days to retrieve activity for"),
) -> ActivityResponseModel:
    activity = {k: 0 for k in get_midnight_dates(days)}

    query = """
        SELECT
            date_trunc('day', created_at::timestamptz at time zone 'utc') AS day,
            count(*)
        FROM
            events
        WHERE
            created_at >= NOW()::TIMESTAMPTZ AT TIME ZONE 'utc' - INTERVAL '30 days'
        AND project_name = $1 AND topic LIKE 'entity.%'
        GROUP BY day
        ORDER BY day DESC;
    """

    async for row in Postgres.iterate(query, project_name):
        activity[row["day"]] = row["count"]

    result = [activity[k] for k in sorted(activity.keys())]
    result = normalize_list(result)

    return ActivityResponseModel(activity=result)


class ProjectTeamsResponseModel(OPModel):
    team_size_active: int = Field(0, description="Number of active team members")
    team_size_total: int = Field(0, description="Total number of team members")
    users_with_access_active: int = Field(0, description="Number of active users")
    users_with_access_total: int = Field(0, description="Total number of users")

    roles: dict[str, int] = Field(
        ...,
        description="Number of users per role",
        example={"artist": 1, "viewer": 2},
    )


@router.get("/users")
async def get_project_teams(
    user: CurrentUser, project_name: ProjectName
) -> ProjectTeamsResponseModel:
    team_members: list[str] = []
    project = await ProjectEntity.load(project_name)
    for team_data in project.data.get("teams", []):
        for member in team_data.get("members", []):
            team_members.append(member["name"])

    role_counts: dict[str, int] = {}
    team_size_active = 0
    team_size_total = 0
    users_with_access_active = 0
    users_with_access_total = 0

    # TODO: do the filtering in the query, save microseconds.
    query = "SELECT name, data, active FROM users"
    async for row in Postgres.iterate(query):
        if row["name"] in team_members:
            team_size_total += 1
            if row["active"]:
                team_size_active += 1

        roles = row["data"].get("roles", {})
        project_roles = roles.get(project_name, [])

        if row["data"].get("isAdmin") or row["data"].get("isManager") or project_roles:
            if row["active"]:
                users_with_access_active += 1
            users_with_access_total += 1

        if not project_roles:
            continue

        for role in project_roles:
            role_counts[role] = role_counts.get(role, 0) + 1

    return ProjectTeamsResponseModel(
        team_size_active=team_size_active,
        team_size_total=team_size_total,
        users_with_access_active=users_with_access_active,
        users_with_access_total=users_with_access_total,
        roles=role_counts,
    )
