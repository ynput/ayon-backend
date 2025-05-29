from typing import Annotated, Any

from fastapi import Path

from ayon_server.api.dependencies import ProjectName
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

GroupingKey = Annotated[str, Path(title="Grouping Key")]


TOP_LEVEL_GROUPING_KEYS = {
    "name": "name",
    "label": "label",
    "status": "status",
    "taskType": "task_type",
    "assignees": "assignees",
    "active": "active",
    "tags": "tags",
}


def parse_grouping_key(key: str) -> str:
    """Parse the grouping key from the path parameter."""
    if nkey := TOP_LEVEL_GROUPING_KEYS.get(key):
        return nkey

    if key.startswith("attrib."):
        attrib_name = key[7:]
        if attribute_library.is_valid("task", attrib_name):
            return f"attrib->'{attrib_name}'"

    raise BadRequestException(f"Invalid grouping key: {key}")


class TaskGroup(OPModel):
    value: Annotated[
        Any,
        Field(
            title="Task Grouping Value",
            description="The value used for grouping tasks.",
            example=["john.doe"],
        ),
    ]

    label: Annotated[
        str | None,
        Field(
            title="Task Grouping Label",
            description="A label for the grouping, if applicable.",
            example="John Doe",
        ),
    ] = None

    icon: Annotated[
        str | None,
        Field(
            title="Task Grouping Icon",
            description="An icon representing the grouping, if applicable.",
            example="user",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Task Grouping Color",
            description="A color associated with the grouping, if applicable.",
            example="#FF5733",
        ),
    ] = None

    count: Annotated[
        int,
        Field(
            title="Task Count",
            description="The number of tasks in this grouping.",
            example=42,
        ),
    ] = 0


class TaskGrouping(OPModel):
    groups: Annotated[
        list[TaskGroup],
        Field(
            title="Task Groups",
            description="List of task groups based on the specified grouping key.",
            example=[
                {
                    "value": "john.doe",
                    "count": 42,
                },
                {
                    "value": "jane.smith",
                    "count": 15,
                },
            ],
        ),
    ]

    key: Annotated[
        str,
        Field(
            title="Grouping Key",
            description="The key used for grouping tasks.",
            example="assignees",
        ),
    ]


async def _get_assignees_groups(project_name: str) -> list[TaskGroup]:
    """Get task groups based on assignees."""
    groups: list[TaskGroup] = []

    query = f"""
        WITH all_assignees AS (
            SELECT unnest(assignees) AS assignee
            FROM project_{project_name}.tasks
        ),
        user_counts AS (
            SELECT count(*) AS count, assignee
            FROM all_assignees
            GROUP BY assignee
        )
        SELECT
            users.name AS name,
            users.attrib->>'fullName' AS label,
            COALESCE(user_counts.count, 0) AS count
        FROM public.users users
        LEFT JOIN user_counts
        ON users.name = user_counts.assignee
    """
    result = await Postgres.fetch(query)
    for row in result:
        group = TaskGroup(
            value=row["name"],
            label=row["label"],
            count=row["count"],
        )
        groups.append(group)
    return groups


async def _get_status_or_task_type_groups(
    project_name: str,
    field: str,
    join_table,
) -> list[TaskGroup]:
    """Get task groups based on status or task type."""
    groups: list[TaskGroup] = []

    query = f"""
        WITH counts AS (
            SELECT count(*) AS count, {field} AS value
            FROM project_{project_name}.tasks
            GROUP BY {field}
        )
        SELECT
            f.name AS value,
            f.data->>'icon' AS icon,
            f.data->>'color' AS color,
            COALESCE(counts.count, 0) AS count
        FROM project_{project_name}.{join_table} f
        LEFT JOIN counts
        ON f.name = counts.value
        AND (f.data->'scope' IS NULL OR f.data->'scope' ? 'task')
    """
    result = await Postgres.fetch(query)
    for row in result:
        group = TaskGroup(
            value=row["value"],
            label=row["value"],
            icon=row["icon"],
            color=row["color"],
            count=row["count"],
        )
        groups.append(group)
    return groups


@router.get(
    "/projects/{project_name}/taskGroups/{grouping_key}",
    response_model_exclude_none=True,
)
async def get_task_groups(
    project_name: ProjectName,
    grouping_key: GroupingKey,
    empty: Annotated[bool, Field(title="Include empty groups")] = False,
) -> TaskGrouping:
    groups: list[TaskGroup] = []

    key = parse_grouping_key(grouping_key)

    if key == "assignees":
        groups = await _get_assignees_groups(project_name)
    elif key in ["status", "task_type"]:
        groups = await _get_status_or_task_type_groups(
            project_name,
            key,
            "statuses" if key == "status" else "task_types",
        )

    #
    # Build the result
    #

    if not empty:
        # Filter out groups with zero count if empty is not requested
        groups = [group for group in groups if group.count > 0]
    return TaskGrouping(groups=groups, key=grouping_key)
