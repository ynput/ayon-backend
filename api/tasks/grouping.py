from typing import Annotated, Any

from fastapi import Path

from ayon_server.api.dependencies import ProjectName
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException
from ayon_server.types import Field, OPModel

from .router import router

GroupingKey = Annotated[str, Path(title="Grouping Key")]


TOP_LEVEL_GROUPING_KEYS = {
    "name": "name",
    "label": "label",
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
        ),
    ]
    count: Annotated[
        int,
        Field(title="Task Count", description="The number of tasks in this grouping."),
    ]


class TaskGrouping(OPModel):
    groups: Annotated[
        list[TaskGroup],
        Field(
            title="Task Groups",
            description="List of task groups based on the specified grouping key.",
        ),
    ]

    key: Annotated[
        str,
        Field(
            title="Grouping Key",
            description="The key used for grouping tasks.",
        ),
    ]


@router.get("/projects/{project_name}/tasks/grouping/{grouping_key}")
async def get_task_grouping(
    project_name: ProjectName,
    grouping_key: GroupingKey,
) -> TaskGrouping:
    result: list[TaskGroup] = []
    return TaskGrouping(groups=result, key=grouping_key)
