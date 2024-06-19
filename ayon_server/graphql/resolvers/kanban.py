import time

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


def bool2sql(value: bool | None) -> str:
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"


async def get_kanban(
    root,
    info: Info,
    last: ARGLast = 2000,
    before: ARGBefore = None,
    projects: list[str] | None = None,
    users: list[str] | None = None,
) -> KanbanConnection:
    user = info.context["user"]

    if not projects:
        projects = []
        async for row in Postgres.iterate("SELECT name FROM projects"):
            if not user.is_manager:
                if row["name"] not in user.data.get("accessGrops", {}):
                    continue
            projects.append(row["name"])

    if not users:
        users = [user.name]

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
        """
        union_queries.append(uq)

    unions = " UNION ALL ".join(union_queries)

    cursor = "updated_at"

    query = f"""
        SELECT
            {cursor} as cursor,
        * FROM ({unions}) dummy
        ORDER BY
            due_date DESC,
            updated_at DESC
    """

    #
    # Execute the query
    #

    start_time = time.monotonic()
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
    end_time = time.monotonic()
    print("Task count", len(res.edges))
    print("Project count", len(projects))
    print(f"Kanban query resolved in {end_time-start_time:.04f}s")
    return res
