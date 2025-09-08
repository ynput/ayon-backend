from typing import Annotated

from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import EntityListsConnection
from ayon_server.graphql.edges import EntityListEdge
from ayon_server.graphql.nodes.entity_list import EntityListNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGIds,
    ARGLast,
    argdesc,
    resolve,
    sortdesc,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.utils import SQLTool, json_loads

SORT_OPTIONS = {
    "label": "label",
    "owner": "created_by",
    "entityListType": "entity_list_type",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "count": "(data->'count')::integer",
    "active": "active",
}

FILTER_OPTIONS = [
    "label",
    "owner",
    "entity_type",
    "entity_list_type",
    "created_at",
    "updated_at",
    "count",
    "active",
    "created_by",
    "updated_by",
]


async def get_entity_lists(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    filter: Annotated[str | None, argdesc("Filter tasks using QueryFilter")] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> EntityListsConnection:
    project_name = root.project_name
    sql_conditions = []

    project = await ProjectEntity.load(project_name)
    user = info.context["user"]
    info.context["project"] = project

    # Load explicit IDs

    if ids:
        if not ids:
            return EntityListsConnection()
        sql_conditions.append(f"id in {SQLTool.id_array(ids)}")

    if user.is_guest:
        sql_conditions.append(f"""
            (
            access->>'guest:{user.attrib.email}' IS NOT NULL
            OR (access->'__guests__')::INTEGER > 0
            )
            """)

    #
    # Filtering
    #

    if filter:
        fdata = json_loads(filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(fq, columns=FILTER_OPTIONS):
            sql_conditions.append(fcond)

    #
    # Pagination and sorting
    #

    order_by = ["creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by == "path":
            order_by = ["hierarchy.path", "tasks.name"]
        else:
            raise BadRequestException(f"Invalid sort_by value: {sort_by}")

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )
    sql_conditions.append(paging_conds)

    #
    # Build the query
    #

    query = f"""
        SELECT {cursor}, *
        FROM project_{project_name}.entity_lists
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """
    #
    # from ayon_server.logging import logger
    #
    # logger.trace(f"QUERY ENTITY LISTS {query}")

    return await resolve(
        EntityListsConnection,
        EntityListEdge,
        EntityListNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        context=info.context,
        order_by=order_by,
    )


async def get_entity_list(root, info: Info, id: str) -> EntityListNode:
    """Return a folder node based on its ID"""
    if not id:
        raise BadRequestException("Entity list ID is not specified")
    connection = await get_entity_lists(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Entity list not found")
    return connection.edges[0].node
