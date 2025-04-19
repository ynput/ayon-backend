from ayon_server.graphql.nodes.entity_list import (
    EntityListItemEdge,
    EntityListItemsConnection,
)
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.utils import SQLTool


async def get_entity_list_items(
    root,
    info: Info,
    entity_list_id: str,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> EntityListItemsConnection:
    project_name = root.project_name
    sql_conditions = [f"entity_list_id = '{entity_list_id}'"]

    order_by = ["position"]
    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )

    sql_conditions.append(paging_conds)
    query = f"""
        SELECT {cursor}, *
        FROM project_{project_name}.entity_list_items
        {SQLTool.conditions(sql_conditions)}
        ORDER BY position ASC
    """

    return await resolve(
        EntityListItemsConnection,
        EntityListItemEdge,
        None,
        query,
        project_name=project_name,
        first=first,
        last=last,
        context=info.context,
        order_by=order_by,
    )
