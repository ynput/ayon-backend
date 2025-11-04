from typing import Annotated, cast

from fastapi import Path, Query

from ayon_server.api.dependencies import (
    CurrentUser,
    PathProjectLevelEntityType,
    ProjectName,
)
from ayon_server.entities.grouping.common import EntityGroup
from ayon_server.entities.grouping.resolvers import (
    get_assignees_groups,
    get_attrib_groups,
    get_product_type_groups,
    get_status_or_type_groups,
    get_tags_groups,
)
from ayon_server.exceptions import BadRequestException
from ayon_server.types import Field, OPModel, ProjectLevelEntityType

from .router import router

GroupingKey = Annotated[str, Path(title="Grouping Key")]


TOP_LEVEL_GROUPING_KEYS = {
    "taskType": "task_type",
    "folderType": "folder_type",
    "productType": "product_type",
    "assignees": "assignees",
    "status": "status",
    "tags": "tags",
}


def parse_grouping_key(key: str) -> str:
    """Parse the grouping key from the path parameter."""
    if nkey := TOP_LEVEL_GROUPING_KEYS.get(key):
        return nkey
    if key.startswith("attrib."):
        return key
    raise BadRequestException(f"Invalid grouping key: {key}")


class EntityGrouping(OPModel):
    groups: Annotated[
        list[EntityGroup],
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

    entity_type: Annotated[
        ProjectLevelEntityType,
        Field(
            title="Entity Type",
            description="The type of entity being grouped, e.g., 'task' or 'folder'.",
            example="task",
        ),
    ]


@router.get("/{entity_type}/{grouping_key}", response_model_exclude_none=True)
async def get_entity_groups(
    user: CurrentUser,
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    grouping_key: GroupingKey,
    empty: Annotated[bool, Query(title="Include empty groups")] = False,
) -> EntityGrouping:
    """Get groups of entities based on the specified key."""

    groups: list[EntityGroup] = []

    key = parse_grouping_key(grouping_key)

    if key == "assignees":
        if entity_type != "task":
            raise BadRequestException(
                "Grouping by assignees is only supported for tasks."
            )
        groups = await get_assignees_groups(project_name)

    elif key in ("status", "task_type", "folder_type"):
        groups = await get_status_or_type_groups(
            project_name,
            entity_type=cast(ProjectLevelEntityType, entity_type),
            key=key,  # type: ignore[arg-type]
        )

    elif key == "product_type":
        groups = await get_product_type_groups(project_name)

    elif key == "tags":
        groups = await get_tags_groups(
            project_name,
            entity_type=cast(ProjectLevelEntityType, entity_type),
        )

    elif key.startswith("attrib."):
        fkey = key[7:]
        groups = await get_attrib_groups(
            project_name,
            entity_type=entity_type,
            key=fkey,
        )

    #
    # Build the result
    #

    if not empty:
        # Filter out groups with zero count if empty is not requested
        groups = [group for group in groups if group.count > 0]
    return EntityGrouping(
        groups=groups,
        key=grouping_key,
        entity_type=entity_type,
    )
