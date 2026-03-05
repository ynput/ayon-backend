# import time

from ayon_server.config import ayonconfig
from ayon_server.entities import UserEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.connections import KanbanConnection
from ayon_server.graphql.edges import KanbanEdge
from ayon_server.graphql.nodes.kanban import KanbanNode
from ayon_server.graphql.resolvers.common import (
    ARGBefore,
    ARGLast,
    resolve,
)
from ayon_server.graphql.types import Info
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import validate_name_list, validate_user_name_list
from ayon_server.utils import SQLTool


def user_has_access(user: UserEntity, project_name: str) -> bool:
    if user.is_manager:
        return True
    return project_name in user.data.get("accessGroups", {})


async def get_accessible_users(user: UserEntity) -> dict[str, set[str]] | None:
    """
    Reurns a dictionary mapping project names to lists of users
    that the given user has access to.

    For managers, this returns None, indicating no restrictions.
    """

    if user.is_manager:
        return None  # No restrictions for managers
    result: dict[str, set[str]] = {}

    if ayonconfig.limit_user_visibility:
        agcond = """WHERE (
            a.access_groups <@ m.access_groups
            OR a.access_groups @> m.access_groups
            OR a.project_name = '__all__'
        )"""
    else:
        agcond = ""

    query = f"""
        WITH all_user_access AS (
            SELECT
                name as user_name,
                jsonb_object_keys(data->'accessGroups') AS project_name
            from users
        ),

        all_user_ag AS (
            SELECT
                u.name user_name,
                CASE WHEN
                    (u.data->>'isAdmin' = 'true' OR u.data->>'isManager' = 'true')
                    THEN '__all__'
                ELSE a.project_name
                END AS project_name,

                u.data->'accessGroups'->a.project_name as access_groups

            FROM users u
            LEFT JOIN all_user_access a ON u.name = a.user_name

            WHERE
                jsonb_array_length(u.data->'accessGroups'->a.project_name) > 0
                OR u.data->>'isAdmin' = 'true' OR u.data->>'isManager' = 'true'
        ),

        my_access AS (
            SELECT
                project_name,
                jsonb_array_elements(data->'accessGroups'->project_name) AS access_group
            FROM users, jsonb_object_keys(data->'accessGroups') AS project_name
            WHERE name = $1
        ),

        my_ag AS (
            SELECT
                u.name user_name,
                a.project_name,
                u.data->'accessGroups'->a.project_name AS access_groups
            FROM users u
            JOIN my_access a
                ON jsonb_array_length(u.data->'accessGroups'->a.project_name) > 0
                WHERE u.name = $1
            GROUP BY u.name, a.project_name, u.data->'accessGroups'->a.project_name
        )

        SELECT
            a.user_name,
            a.project_name
        FROM all_user_ag a
        JOIN my_ag m ON (a.project_name = m.project_name OR a.project_name = '__all__')
        {agcond}
        ORDER BY a.user_name, a.project_name;
    """

    async for row in Postgres.iterate(query, user.name):
        user_name = row["user_name"]
        project_name = row["project_name"]

        if project_name not in result:
            result[project_name] = set()

        result[project_name].add(user_name)

    return result


async def get_kanban(
    root,
    info: Info,
    last: ARGLast = 2000,
    before: ARGBefore = None,
    projects: list[str] | None = None,
    assignees_any: list[str] | None = None,
    task_ids: list[str] | None = None,
) -> KanbanConnection:
    """
    Fetches tasks for the Kanban board.

    Parameters
    ----------
    last : ARGLast, optional
        The number of tasks to return, by default 2000.

    before : ARGBefore, optional
        The cursor to fetch tasks before, by default None.

    projects : list[str], optional
        List of project IDs to filter tasks.
        If not specified, tasks from all projects are listed.
        For non-managers, the result is limited to projects the user has access to.
        Inactive projects are never included.

    assignees_any : list[str], optional
        List of user names to filter tasks.
        If the invoking user is a manager, tasks assigned
        to the specified users are listed.
        If not provided, all tasks are listed regardless of assignees.

    task_ids : list[str], optional
        If set, return explicit tasks by their IDs.
        This is used for fetching updates when a entity.task.* event is received.

    Returns
    -------
    KanbanConnection
        A connection object containing the fetched tasks.

    """
    user = info.context["user"]
    if user.is_guest:
        return KanbanConnection(edges=[])

    project_data: list[dict[str, str]] = []

    project_defaults = attribute_library.project_defaults
    DEFAULT_PRIORITY = project_defaults.get("priority", "normal")

    if not projects:
        q = "SELECT name, code FROM public.projects WHERE active IS TRUE"
    else:
        validate_name_list(projects)
        q = f"""
            SELECT
                name,
                code,
                attrib->>'priority' as priority
            FROM public.projects
            WHERE name = ANY({SQLTool.array(projects, curly=True)})
        """
    async for row in Postgres.iterate(q):
        project_data.append(row)

    if not user.is_manager:
        project_data = [p for p in project_data if user_has_access(user, p["name"])]

    elif assignees_any:
        validate_user_name_list(assignees_any)

    if not project_data:
        return KanbanConnection(edges=[])

    # Sub-query conditions

    sub_query_conds = []

    if task_ids:
        # id_array sanitizes the input
        c = f"t.id IN {SQLTool.id_array(task_ids)}"
        sub_query_conds.append(c)

    umap = await get_accessible_users(user)

    union_queries = []
    for pdata in project_data:
        project_name = pdata["name"]
        project_code = pdata["code"]
        project_schema = f"project_{project_name}"
        project_priority = pdata.get("priority") or DEFAULT_PRIORITY

        ucond = ""
        if umap is None:
            if assignees_any:
                # assignees list is already sanitized at this point
                ucond = f"t.assignees && {SQLTool.array(assignees_any, curly=True)}"
        else:
            try:
                project_permissions = user.permissions(project_name)
            except ForbiddenException:
                continue

            if project_permissions.read.enabled:
                # user has restricted read access.
                # limit assignees to themselves

                users = {user.name}

            else:
                users = umap.get(project_name, set())
                users = users.union(umap.get("__all__", set()))
                if assignees_any:
                    users = users.intersection(assignees_any)

            if users:
                ucond = f"t.assignees && {SQLTool.array(list(users), curly=True)}"
            else:
                # No accessible users, skip this project
                continue

        sq_conds = sub_query_conds.copy()
        if ucond:
            sq_conds.append(ucond)

        uq = f"""
            SELECT
                '{project_name}' AS project_name,
                '{project_code}' AS project_code,
                '{project_priority}' AS project_priority,
                t.id as id,
                t.name as name,
                t.label as label,
                t.status as status,
                t.tags as tags,
                t.task_type as task_type,
                t.assignees as assignees,
                t.updated_at as updated_at,
                t.created_at as created_at,
                t.attrib->>'endDate' as due_date,
                t.attrib->>'priority' as priority,
                f.id as folder_id,
                f.name as folder_name,
                f.label as folder_label,
                h.path as folder_path,
                h.attrib->>'priority' as folder_priority,
                t.thumbnail_id as thumbnail_id,
                t.data->'thumbnailInfo' as thumbnail_info,
                EXISTS (
                    SELECT 1 FROM {project_schema}.versions v
                    INNER JOIN {project_schema}.activity_feed af
                    ON  af.entity_id = v.id
                    AND af.entity_type = 'version'
                    AND af.activity_type = 'reviewable'
                    AND v.task_id = t.id
                ) AS has_reviewables
                FROM {project_schema}.tasks t
                JOIN {project_schema}.folders f ON f.id = t.folder_id
                JOIN {project_schema}.exported_attributes h ON h.folder_id = f.id
                {SQLTool.conditions(sq_conds)}
        """
        union_queries.append(uq)

    if not union_queries:
        # This should not normally happen, but if it does,
        # return an empty result instead of an error
        logger.warning(
            "No union queries generated for Kanban fetch, returning empty result"
        )
        return KanbanConnection(edges=[])

    unions = " UNION ALL ".join(union_queries)
    cursor = "updated_at"

    query = f"""
        SELECT
            {cursor} as cursor,
        * FROM ({unions}) dummy
        ORDER BY
            due_date DESC NULLS LAST,
            updated_at DESC
    """

    #
    # Execute the query
    #

    res = await resolve(
        KanbanConnection,
        KanbanEdge,
        KanbanNode,
        query,
        last=last,
        context=info.context,
    )
    return res
