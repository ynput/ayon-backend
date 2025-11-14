from typing import Annotated

from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import WorkfilesConnection
from ayon_server.graphql.edges import WorkfileEdge
from ayon_server.graphql.nodes.workfile import WorkfileNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool, slugify

SORT_OPTIONS = {
    "name": "workfiles.name",
    "status": "workfiles.status",
    "createdAt": "workfiles.created_at",
    "updatedAt": "workfiles.updated_at",
}


async def get_workfiles(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    paths: Annotated[list[str] | None, argdesc("List of paths to filter by")] = None,
    path_ex: Annotated[str | None, argdesc("Match paths by regular expression")] = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
    search: Annotated[str | None, argdesc("Fuzzy text search filter")] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> WorkfilesConnection:
    """Return a list of workfiles."""

    project_name = root.project_name
    user = info.context["user"]
    fields = FieldInfo(info, ["workfiles.edges.node", "workfile"])

    if user.is_guest:
        return WorkfilesConnection(edges=[])

    #
    # SQL
    #

    sql_columns = ["workfiles.*"]

    # sql_joins = []
    sql_conditions = []
    sql_joins = []

    if ids is not None:
        if not ids:
            return WorkfilesConnection()
        sql_conditions.append(f"workfiles.id IN {SQLTool.id_array(ids)}")

    if task_ids is not None:
        if not task_ids:
            return WorkfilesConnection()
        sql_conditions.append(f"workfiles.task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"workfiles.task_id = '{root.id}'")

    if paths is not None:
        if not paths:
            return WorkfilesConnection()
        paths = [r.replace("'", "''") for r in paths]
        sql_conditions.append(f"workfiles.path IN {SQLTool.array(paths)}")

    if path_ex:
        # TODO: is this safe?
        path_ex = path_ex.replace("'", "''").replace("\\", "\\\\")
        sql_conditions.append(f"workfiles.path ~ '{path_ex}'")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "workfiles.id", has_links)
        )

    if statuses is not None:
        if not statuses:
            return WorkfilesConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"workfiles.status IN {SQLTool.array(statuses)}")
    if tags is not None:
        if not tags:
            return WorkfilesConnection()
        validate_name_list(tags)
        sql_conditions.append(f"workfiles.tags @> {SQLTool.array(tags, curly=True)}")

    access_list = await create_folder_access_list(root, info)
    if access_list is not None or search or fields.any_endswith("parents"):
        sql_columns.extend(
            [
                "tasks.name AS _task_name",
                "hierarchy.path AS _folder_path",
            ]
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.tasks AS tasks
                ON tasks.id = workfiles.task_id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON hierarchy.id = tasks.folder_id
                """,
            ]
        )

        if access_list is not None:
            sql_conditions.append(
                f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
            )

    if search:
        terms = slugify(search, make_set=True, min_length=2)
        for term in terms:
            sub_conditions = []
            term = term.replace("'", "''")  # Escape single quotes
            sub_conditions.append(f"tasks.name ILIKE '%{term}%'")
            sub_conditions.append(f"tasks.task_type ILIKE '%{term}%'")
            sub_conditions.append(f"hierarchy.path ILIKE '%{term}%'")
            sub_conditions.append(f"workfiles.path ILIKE '%{term}%'")

            condition = " OR ".join(sub_conditions)
            sql_conditions.append(f"({condition})")

    #
    # Pagination
    #

    order_by = ["workfiles.creation_order"]

    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"workfiles.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )
    sql_conditions.append(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.workfiles AS workfiles
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    return await resolve(
        WorkfilesConnection,
        WorkfileEdge,
        WorkfileNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_workfile(root, info: Info, id: str) -> WorkfileNode:
    """Return a task node based on its ID"""
    if not id:
        raise BadRequestException("Workfile ID not specified")
    connection = await get_workfiles(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Workfile not found")
    return connection.edges[0].node
