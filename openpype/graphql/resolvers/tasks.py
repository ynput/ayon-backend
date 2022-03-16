from typing import Annotated

from strawberry.types import Info

from openpype.utils import EntityID, SQLTool

from ..connections import TasksConnection
from ..edges import TaskEdge
from ..nodes.task import TaskNode
from .common import ARGAfter, ARGBefore, ARGFirst, ARGIds, ARGLast, argdesc, resolve


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

    project_name = root.project_name

    if folder_ids == ["root"]:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    #
    # Conditions
    #

    conditions = []

    if ids:
        conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if name:
        conditions.append(f"name ILIKE '{name}'")

    if folder_ids:
        conditions.append(f"folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        conditions.append(f"folder_id = '{root.id}'")

    if task_types:
        conditions.append(f"task_type IN {SQLTool.array(task_types)}")

    #
    # Pagination
    #

    if not (last or first):
        first = 100

    pagination = ""
    order_by = "name"
    if first:
        pagination += f"ORDER BY {order_by} ASC LIMIT {first}"
        if after:
            conditions.append(f"{order_by} > '{EntityID.parse(after)}'")
    elif last:
        pagination += f"ORDER BY {order_by} DESC LIMIT {first}"
        if before:
            conditions.append(f"{order_by} < '{EntityID.parse(before)}'")

    #
    # Query
    #

    query = f"""
        SELECT *
        FROM project_{project_name}.tasks
        {SQLTool.conditions(conditions)}
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
