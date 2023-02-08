from fastapi import Depends, Query

from ayon_server.api.dependencies import dep_current_user, dep_project_name
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .router import router


class EntityCounts(OPModel):
    folders: int = Field(..., description="Number of folders", example=10)
    subsets: int = Field(..., description="Number of subsets", example=98)
    versions: int = Field(..., description="Number of versions", example=512)
    representations: int = Field(
        ...,
        description="Number of representations",
        example=4853,
    )
    tasks: int = Field(..., description="Number of tasks", example=240)
    workfiles: int = Field(..., description="Number of workfiles", example=190)


@router.get("/entities", response_model=EntityCounts)
async def get_project_entity_counts(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Retrieve entity counts for a given project."""

    counts = {}
    for entity_type in ProjectLevelEntityType.__args__:
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
    percentage: float = Field(
        ..., description="Percentage of tasks completed", example=0.5
    )
    behind: int = Field(
        ...,
        description="Number of days tasks are not completed after due date",
        example=5,
    )
    ahead: int = Field(
        ..., description="Number of days tasks are completed before due date", example=3
    )


class HealthStorageUsage(OPModel):
    quota: int = Field(..., description="Storage quota", example=1000000000)
    used: int = Field(..., description="Storage used", example=500000000)


class HealthTasks(OPModel):
    total: int = Field(..., description="Total number of tasks", example=100)
    completed: int = Field(..., description="Number of completed tasks", example=50)
    overdue: int = Field(..., description="Number of overdue tasks", example=10)
    upcoming: int = Field(..., description="Number of upcoming tasks", example=40)


class Health(OPModel):
    completion: HealthCompletion = Field(..., description="Task completion")
    storage_usage: HealthStorageUsage = Field(..., description="Storage usage")
    tasks: HealthTasks = Field(..., description="Task statistics")
    statuses: dict[str, int] = Field(..., description="Task status statistics")


@router.get("/health", response_model=Health)
async def get_project_health(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):

    project = await ProjectEntity.load(project_name)

    #
    # Statuses
    #

    query = f"""
        SELECT status, count(status) as count
        FROM project_{project_name}.tasks GROUP BY status
    """
    res = await Postgres.fetch(query)
    statuses = {row["status"]: row["count"] for row in res}

    #
    # Tasks
    #

    total_tasks = sum(statuses.values())
    completed_tasks = 0
    overdue_tasks = 0
    upcoming_tasks = 0
    for status in project.statuses:
        if status.get("state") == "done":
            completed_tasks += statuses.get(status["name"], 0)

        if status.get("state") == "in_progress":
            # TODO: Check if task is overdue
            overdue_tasks += statuses.get(status["name"], 0)

        if status.get("state") in ("in_progress", "blocked"):
            upcoming_tasks += statuses.get(status["name"], 0)

    tasks = {
        "total": total_tasks,
        "completed": completed_tasks,
        "overdue": overdue_tasks,
        "upcoming": upcoming_tasks,
    }

    #
    # Completion
    #

    percentage = ((completed_tasks / total_tasks) if total_tasks else 0) * 100
    completion = {
        "percentage": percentage,
        "behind": 0,
        "ahead": 0,
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


@router.get("/activity", response_model=ActivityResponseModel)
async def get_project_activity(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    days: int = Query(50, description="Number of days to retrieve activity for"),
):

    import hashlib

    # TODO!

    def string_to_hash_list(input_string):
        hash_object = hashlib.sha256(input_string.encode())
        hex_dig = hash_object.hexdigest()
        hash_list = []
        for i in range(days):
            hash_list.append(int(hex_dig[i % 64], 16) % 100)
        return hash_list

    return ActivityResponseModel(activity=string_to_hash_list(project_name))
