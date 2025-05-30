from typing import Literal

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger

from .common import TaskGroup


async def get_status_or_type_groups(
    project_name: str,
    entity_type: Literal["task", "folder"],
    key: Literal["status", "task_type", "folder_type"],
) -> list[TaskGroup]:
    """Get task groups based on status or entity subtype.

    This works with folder and task entities
    """

    if key == "task_type":
        if entity_type != "task":
            raise ValueError("key 'task_type' can only be used with tasks.")
        join_table = "task_types"
    elif key == "folder_type":
        if entity_type != "folder":
            raise ValueError("key 'folder_type' can only be used with folders.")
        join_table = "folder_types"
    elif key == "status":
        join_table = "statuses"
    else:
        raise ValueError(f"Invalid key: {key}")

    groups: list[TaskGroup] = []

    query = f"""
        WITH counts AS (
            SELECT count(*) AS count, {key} AS value
            FROM project_{project_name}.{entity_type}s
            GROUP BY {key}
        )
        SELECT
            f.name AS value,
            f.data->>'icon' AS icon,
            f.data->>'color' AS color,
            COALESCE(counts.count, 0) AS count
        FROM project_{project_name}.{join_table} f
        LEFT JOIN counts
        ON f.name = counts.value
        AND (f.data->'scope' IS NULL OR f.data->'scope' ? '{entity_type}')
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


async def get_assignees_groups(project_name: str) -> list[TaskGroup]:
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


async def get_attrib_groups(
    project_name: str,
    entity_type: Literal["task", "folder"],
    key: str,
) -> list[TaskGroup]:
    """Get task groups based on custom attributes."""
    groups: list[TaskGroup] = []

    if not attribute_library.is_valid(entity_type, key):
        raise BadRequestException(f"Invalid {entity_type} attribute {key}")

    attr_config = attribute_library.by_name(key)

    attr_type = attr_config.get("type", "string")
    attr_enum = attr_config.get("enum")

    if attr_type.startswith("list_of"):
        raise NotImplementedError("Grouping by list attributes is not supported.")

    enum_dict = {}
    if attr_enum:
        for item in attr_enum:
            enum_dict[item["value"]] = {
                "label": item.get("label"),
                "icon": item.get("icon"),
                "color": item.get("color"),
            }

    logger.debug(f"Attr config: {attr_config}")
    logger.debug(f"enum_dict: {enum_dict}")

    if entity_type == "task":
        values_cte = f"""
            SELECT
                COALESCE(t.attrib->'{key}', ex.attrib->'{key}') AS value
            FROM project_{project_name}.tasks t
            JOIN project_{project_name}.exported_attributes ex
            ON t.folder_id = ex.folder_id
            WHERE t.attrib ? '{key}' OR ex.attrib ? '{key}'
        """

    else:
        raise NotImplementedError("Grouping by folder attributes is not supported.")

    query = f"""
        WITH values AS ({values_cte})
        SELECT
            values.value AS value,
            COUNT(*) AS count
        FROM values
        GROUP BY values.value
    """
    result = await Postgres.fetch(query)

    for row in result:
        value = row["value"]
        count = row["count"]

        meta = enum_dict.pop(value, {})

        group = TaskGroup(value=value, count=count, **meta)
        groups.append(group)

    for value, meta in enum_dict.items():
        group = TaskGroup(value=value, **meta, count=0)
        groups.append(group)

    return groups
