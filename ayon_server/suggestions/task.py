from collections import defaultdict

from ayon_server.entities import ProjectEntity, TaskEntity, UserEntity
from ayon_server.lib.postgres import Postgres

from .common import get_relevant_users_cte
from .models import (
    FolderSuggestionItem,
    ProductSuggestionItem,
    SuggestionType,
    TaskSuggestionItem,
    UserSuggestionItem,
    VersionSuggestionItem,
)


async def get_task_suggestions(
    project: ProjectEntity,
    user: UserEntity,
    task: TaskEntity,
) -> dict[str, list[SuggestionType]]:
    """
    Assignees: Every assignee in the project, sorted by assignees first.
    Versions: Every version linked to the task.
    Tasks: Direct sibling tasks to the task.
    """

    project_name = task.project_name
    result: defaultdict[str, list[SuggestionType]] = defaultdict(list)
    item: SuggestionType
    parent: FolderSuggestionItem | ProductSuggestionItem

    # get users:

    relevant_users_cte = await get_relevant_users_cte(project, user)

    query = f"""
        WITH {relevant_users_cte}

        SELECT
            u.name as name,
            u.attrib->>'fullName' as label,
            r.rel_count as has_task
        FROM public.users u

        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.tasks t
            WHERE
                t.assignees @> ARRAY[u.name]
                AND t.id = $1
        ) r ON true

        WHERE
            u.name IN (SELECT name FROM relevant_users)
        ORDER BY
            r.rel_count DESC,
            u.name;
    """

    async for row in Postgres.iterate(query, task.id):
        item = UserSuggestionItem(
            name=row["name"],
            full_name=row["label"] or None,
            relevance=row["has_task"],
            created_at=None,
        )
        result.setdefault("users", []).append(item)

    # get versions:

    query = f"""
        SELECT
            v.id as version_id,
            v.version as version,
            v.created_at as created_at,
            p.name as product_name,
            p.product_type as product_type,
            p.id as product_id
        FROM project_{project_name}.versions v
        JOIN project_{project_name}.products p ON v.product_id = p.id
        JOIN project_{project_name}.tasks t ON v.task_id = t.id
        WHERE t.id = $1
        ORDER BY v.version;
    """

    async for row in Postgres.iterate(query, task.id):
        parent = ProductSuggestionItem(
            id=row["product_id"],
            name=row["product_name"],
            product_type=row["product_type"],
            created_at=None,
            relevance=None,
            parent=None,
        )
        item = VersionSuggestionItem(
            id=row["version_id"],
            version=row["version"],
            created_at=row["created_at"],
            parent=parent,
            relevance=0,
        )
        result["versions"].append(item)

    # get tasks:

    query = f"""
        SELECT
            t.id as task_id,
            t.name as name,
            t.label as label,
            t.task_type as task_type,
            t.created_at as created_at,
            t.thumbnail_id as thumbnail_id,

            f.id as folder_id,
            f.name as folder_name,
            f.label as folder_label,
            f.folder_type as folder_type,
            f.thumbnail_id as thumbnail_id,
            f.created_at as folder_created_at
        FROM project_{task.project_name}.tasks t
        JOIN project_{task.project_name}.folders f ON t.folder_id = f.id
        WHERE f.id = $1
        ORDER BY t.name;
    """

    async for row in Postgres.iterate(query, task.folder_id):
        parent = FolderSuggestionItem(
            id=row["folder_id"],
            name=row["folder_name"],
            label=row["folder_label"],
            folder_type=row["folder_type"],
            created_at=row["folder_created_at"],
            thumbnail_id=row["thumbnail_id"],
            relevance=None,
        )
        item = TaskSuggestionItem(
            id=row["task_id"],
            name=row["name"],
            label=row["label"],
            task_type=row["task_type"],
            created_at=row["created_at"],
            thumbnail_id=row["thumbnail_id"],
            parent=parent,
            relevance=0,
        )
        result["tasks"].append(item)

    return result
