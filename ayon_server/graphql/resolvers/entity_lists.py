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
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.utils import SQLTool


async def get_entity_lists(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
) -> EntityListsConnection:
    project_name = root.project_name
    sql_conditions = []

    # Allow access to managers, owners and explicitly shared lists
    user = info.context["user"]
    if not user.is_manager:
        sql_conditions.append(f"(created_by='{user.name}' OR access ? '{user.name}'")

    #
    # Pagination
    #

    order_by = ["created_at", "creation_order"]
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
