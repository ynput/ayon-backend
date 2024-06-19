# import time

from ayon_server.entities import UserEntity
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
from ayon_server.types import validate_name_list
from ayon_server.utils import SQLTool


def bool2sql(value: bool | None) -> str:
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"


def user_has_access(user: UserEntity, project_name: str) -> bool:
    if user.is_manager:
        return True
    return project_name in user.data.get("accessGroups", {})


async def get_kanban(
    root,
    info: Info,
    last: ARGLast = 2000,
    before: ARGBefore = None,
    projects: list[str] | None = None,
    assignees: list[str] | None = None,
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

    assignees : list[str], optional
        List of user names to filter tasks.
        If the invoking user is a manager, tasks assigned
        to the specified users are listed.
        If not provided, all tasks are listed regardless of assignees.
        For non-managers, this is always set to [user.name].

    Returns
    -------
    KanbanConnection
        A connection object containing the fetched tasks.

    """
    user = info.context["user"]

    if not projects:
        projects = []
        q = "SELECT name FROM projects WHERE active IS TRUE"
        async for row in Postgres.iterate(q):
            projects.append(row["name"])

    if not user.is_manager:
        assignees = [user.name]
        projects = [p for p in projects if user_has_access(user, p)]
    elif assignees:
        validate_name_list(assignees)

    sub_query_conds = []
    if assignees:
        c = f"t.assignees @> {SQLTool.array(assignees, curly=True)}"
        sub_query_conds.append(c)

    union_queries = []
    for project_name in projects:
        project_schema = f"project_{project_name}"
        uq = f"""
            SELECT
                '{project_name}' AS project_name,
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
                f.id as folder_id,
                f.name as folder_name,
                f.label as folder_label,
                h.path as folder_path,
                t.thumbnail_id as thumbnail_id,
                NULL as last_version_with_thumbnail_id
                FROM {project_schema}.tasks t
                JOIN {project_schema}.folders f ON f.id = t.folder_id
                JOIN {project_schema}.hierarchy h ON h.id = f.id
                {SQLTool.conditions(sub_query_conds)}
        """
        union_queries.append(uq)

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

    # start_time = time.monotonic()
    res = await resolve(
        KanbanConnection,
        KanbanEdge,
        KanbanNode,
        None,
        query,
        None,
        last,
        context=info.context,
    )
    # end_time = time.monotonic()
    # print("Task count", len(res.edges))
    # print("Project count", len(projects))
    # print(f"Kanban query resolved in {end_time-start_time:.04f}s")
    return res
