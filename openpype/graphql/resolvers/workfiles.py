from typing import Annotated

from strawberry.types import Info

from openpype.graphql.connections import WorkfilesConnection
from openpype.graphql.edges import WorkfileEdge
from openpype.graphql.nodes.workfile import WorkfileNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
)
from openpype.utils import SQLTool


async def get_workfiles(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    has_links: ARGHasLinks = None,
) -> WorkfilesConnection:
    """Return a list of workfiles."""

    project_name = root.project_name

    #
    # SQL
    #

    sql_columns = [
        "workfiles.id AS id",
        "workfiles.path AS path",
        "workfiles.task_id AS task_id",
        "workfiles.thumbnail_id AS thumbnail_id",
        "workfiles.created_by AS created_by",
        "workfiles.updated_by AS updated_by",
        "workfiles.attrib AS attrib",
        "workfiles.data AS data",
        "workfiles.active AS active",
        "workfiles.created_at AS created_at",
        "workfiles.updated_at AS updated_at",
        "workfiles.creation_order AS creation_order",
    ]

    # sql_joins = []
    sql_conditions = []
    sql_joins = []

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if task_ids:
        sql_conditions.append(f"task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"task_id = '{root.id}'")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "workfiles.id", has_links)
        )

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.tasks AS tasks
                ON task.id = workfiles.task_id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON hierarchy.id = tasks.folder_id
                """,
            ]
        )

    #
    # Pagination
    #

    order_by = "workfiles.creation_order"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {", ".join(sql_columns)}
        FROM project_{project_name}.workfiles AS workfiles
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        WorkfilesConnection,
        WorkfileEdge,
        WorkfileNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
        order_by=order_by,
    )


async def get_workfile(root, info: Info, id: str) -> WorkfileNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_workfiles(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
