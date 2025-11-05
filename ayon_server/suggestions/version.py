from collections import defaultdict

from ayon_server.entities import ProjectEntity, UserEntity, VersionEntity
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


async def get_version_suggestions(
    project: ProjectEntity,
    user: UserEntity,
    version: VersionEntity,
) -> dict[str, list[SuggestionType]]:
    """
    Assignees: Every assignee in the project, sorted by author first.
    Versions: Direct sibling versions to the version.
    Tasks: Direct sibling tasks to the parent task of the version.
    """

    project_name = version.project_name
    result: defaultdict[str, list[SuggestionType]] = defaultdict(list)
    item: SuggestionType
    parent: ProductSuggestionItem | FolderSuggestionItem

    # get users:

    relevant_users_cte = await get_relevant_users_cte(project, user)

    query = f"""
        WITH {relevant_users_cte}
        SELECT
            u.name as name,
            u.attrib->>'fullName' as full_name,

            (COALESCE(aref.rel_count, 0) * 15)   -- active in comments
            + (COALESCE(vref.rel_count, 0) * 10) -- author of the version
            + (COALESCE(tref.rel_count, 0) * 5)  -- assignees on the task
            + COALESCE(pref.rel_count, 0)        -- authors of sibling versions
            as relevance


        FROM public.users u

        -- author
        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.versions v
            WHERE v.author = u.name
            AND v.id = $1
        ) vref ON true

        -- authors of siblings
        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.versions v
            WHERE v.author = u.name
            AND v.product_id = $2
        ) pref ON true

        -- assignees
        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.tasks t
            JOIN project_{project_name}.versions v
                ON t.id = v.task_id
            WHERE t.assignees @> ARRAY[u.name]
            AND v.task_id = t.id
            AND v.id = $1
        ) tref ON true

        LEFT JOIN LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.activity_feed ar
            WHERE ar.entity_id = $1
            AND ar.reference_type = 'origin'
            AND ar.activity_data->>'author' = u.name
        ) aref ON true

        WHERE
            u.name IN (SELECT name FROM relevant_users)

        ORDER BY
            aref.rel_count DESC,
            vref.rel_count DESC,
            tref.rel_count DESC,
            pref.rel_count DESC,
            u.name ASC
    """

    async for row in Postgres.iterate(query, version.id, version.product_id):
        item = UserSuggestionItem(
            name=row["name"],
            full_name=row["full_name"],
            relevance=row["relevance"],
            created_at=None,
        )
        result["users"].append(item)

    # Get versions

    query = f"""
        SELECT
            v.id as version_id,
            v.version as version,
            v.thumbnail_id as thumbnail_id,
            v.created_at as created_at,
            p.id as product_id,
            p.name as product_name,
            p.product_type as product_type,
            p.created_at as product_created_at
        FROM project_{project_name}.versions v
        JOIN project_{project_name}.products p ON v.product_id = p.id
        WHERE v.product_id = $1
        AND v.id != $2
        ORDER BY v.version;
    """

    async for row in Postgres.iterate(query, version.product_id, version.id):
        parent = ProductSuggestionItem(
            id=row["product_id"],
            name=row["product_name"],
            product_type=row["product_type"],
            created_at=row["product_created_at"],
            parent=None,
            relevance=None,
        )

        item = VersionSuggestionItem(
            id=row["version_id"],
            version=row["version"],
            created_at=row["created_at"],
            parent=parent,
            relevance=0,
        )
        result["versions"].append(item)

    # Get tasks

    query = f"""
        SELECT
            t.id as task_id,
            t.name as task_name,
            t.label as task_label,
            t.task_type as task_type,
            t.thumbnail_id as thumbnail_id,
            t.created_at as created_at,

            f.id as folder_id,
            f.name as folder_name,
            f.label as folder_label,
            f.folder_type as folder_type,
            f.created_at as folder_created_at,
            f.thumbnail_id as folder_thumbnail_id

        FROM project_{project_name}.versions v
        JOIN project_{project_name}.products p ON v.product_id = p.id
        JOIN project_{project_name}.folders f on p.folder_id = f.id
        JOIN project_{project_name}.tasks t on t.folder_id = f.id
        WHERE v.id = $1
    """

    async for row in Postgres.iterate(query, version.id):
        parent = FolderSuggestionItem(
            id=row["folder_id"],
            name=row["folder_name"],
            folder_type=row["folder_type"],
            label=row["folder_label"],
            created_at=row["folder_created_at"],
            thumbnail_id=row["folder_thumbnail_id"],
            relevance=None,
        )

        item = TaskSuggestionItem(
            id=row["task_id"],
            name=row["task_name"],
            label=row["task_label"] or None,
            task_type=row["task_type"],
            created_at=row["created_at"],
            thumbnail_id=row["thumbnail_id"],
            parent=parent,
            relevance=0,
        )
        result["tasks"].append(item)

    return result
