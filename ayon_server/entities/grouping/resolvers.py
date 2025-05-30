from typing import Literal

from ayon_server.lib.postgres import Postgres

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
