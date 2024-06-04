from collections import defaultdict

from ayon_server.entities import FolderEntity
from ayon_server.lib.postgres import Postgres

from .models import (
    FolderSuggestionItem,
    TaskSuggestionItem,
    UserSuggestionItem,
)

STYPE = list[UserSuggestionItem | TaskSuggestionItem]


async def get_folder_suggestions(
    user: str,
    folder: FolderEntity,
) -> dict[str, STYPE]:
    """
    Assignees: Every assignee in the project
    Versions: Disabled - what versions would you want to see on a folder?
    Tasks: Direct child tasks of the folder.
    """

    project_name = folder.project_name

    result: defaultdict[str, STYPE] = defaultdict(list)

    # get users:

    query = f"""
        WITH relevant_users AS (
            SELECT unnest(t.assignees) as name
            FROM project_{project_name}.tasks t
        )

        SELECT
            u.name as name,
            u.attrib->>'fullName' as label,
            r.rel_count as has_task
        FROM users u
        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.tasks t
            JOIN project_{project_name}.hierarchy h ON t.folder_id = h.id
            WHERE
                t.assignees @> ARRAY[u.name]
                AND h.path LIKE '{folder.path.lstrip("/")}%'
        ) r ON true
        WHERE
            u.name IN (SELECT name FROM relevant_users)
        AND u.name != $1
        ORDER BY
            r.rel_count DESC,
            u.name;
    """

    async for row in Postgres.iterate(query, user):
        item = UserSuggestionItem(
            name=row["name"],
            full_name=row["label"] or None,
            relevance=row["has_task"],
            created_at=None,
        )
        result["users"].append(item)

    # Get tasks

    query = f"""
    SELECT
        t.id as task_id,
        t.task_type as task_type,
        t.name as task_name,
        t.label as task_label,
        t.thumbnail_id as task_thumbnail_id,
        t.created_at as task_created_at,
        f.id as folder_id,
        f.name as folder_name,
        f.label as folder_label,
        f.folder_type as folder_type,
        f.thumbnail_id as folder_thumbnail_id,
        f.created_at as folder_created_at
    FROM project_{project_name}.tasks t
    JOIN project_{project_name}.folders f ON t.folder_id = f.id
    ORDER BY t.name ASC;
    """

    async for row in Postgres.iterate(query):
        parent = FolderSuggestionItem(
            id=row["folder_id"],
            folder_type=row["folder_type"],
            name=row["folder_name"],
            label=row["folder_label"] or None,
            thumbnail_id=row["folder_thumbnail_id"] or None,
            created_at=row["folder_created_at"],
            relevance=None,
        )
        result["tasks"].append(
            TaskSuggestionItem(
                id=row["task_id"],
                task_type=row["task_type"],
                name=row["task_name"],
                label=row["task_label"] or None,
                thumbnail_id=row["task_thumbnail_id"],
                created_at=row["task_created_at"],
                parent=parent,
                relevance=0,
            )
        )

    return result
