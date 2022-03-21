from typing import Annotated

from strawberry.types import Info

from openpype.utils import SQLTool

from ..connections import TasksConnection
from ..edges import TaskEdge
from ..nodes.task import TaskNode
from .common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGIds,
    ARGLast,
    argdesc,
    resolve,
    create_folder_access_list,
    create_pagination,
    FieldInfo,
)


async def get_tasks(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    task_types: Annotated[
        list[str] | None, argdesc("List of task types to filter by")
    ] = None,
    folder_ids: Annotated[
        list[str] | None, argdesc("List of parent folder IDs to filter by")
    ] = None,
    name: Annotated[str | None, argdesc("Text string to filter name by")] = None,
) -> TasksConnection:
    """Return a list of tasks."""

    if folder_ids == ["root"]:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    project_name = root.project_name
    fields = FieldInfo(info, ["tasks.edges.node", "subset"])

    #
    # SQL
    #

    sql_columns = [
        "tasks.id AS id",
        "tasks.name AS name",
        "tasks.folder_id AS folder_id",
        "tasks.task_type AS task_type",
        "tasks.assignees AS assignees",
        "tasks.attrib AS attrib",
        "tasks.data AS data",
        "tasks.active AS active",
        "tasks.created_at AS created_at",
        "tasks.updated_at AS updated_at",
    ]
    sql_conditions = []
    sql_joins = []

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if folder_ids:
        sql_conditions.append(f"folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"folder_id = '{root.id}'")

    if name:
        sql_conditions.append(f"name ILIKE '{name}'")

    if task_types:
        sql_conditions.append(f"task_type IN {SQLTool.array(task_types)}")

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

    #
    # Joins
    #

    if "folder" in fields or (access_list is not None):
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.folder_type AS _folder_folder_type",
                "folders.parent_id AS _folder_parent_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
            ]
        )
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = tasks.folder_id
            """
        )

        if any(
            field.endswith("folder.path") or field.endswith("folder.parents")
            for field in fields
        ) or (access_list is not None):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"""
                LEFT JOIN project_{project_name}.hierarchy AS hierarchy
                ON folders.id = hierarchy.id
                """
            )

    #
    # Pagination
    #

    # TODO: ordering by name breaks pagination because using name as a cursor
    # is not the best idea ever. It skips duplicate names, so it only makes sense
    # for querying tasks of one folder

    order_by = "name"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {", ".join(sql_columns)}
        FROM project_{project_name}.tasks AS tasks
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        TasksConnection,
        TaskEdge,
        TaskNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
        order_by=order_by,
    )


async def get_task(root, info: Info, id: str) -> TaskNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_tasks(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
