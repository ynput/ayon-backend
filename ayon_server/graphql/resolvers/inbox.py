from strawberry.types import Info

from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.edges import ActivityEdge
from ayon_server.graphql.nodes.activity import ActivityNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    FieldInfo,
    create_pagination,
    resolve,
)
from ayon_server.utils import SQLTool


def bool2sql(value: bool | None) -> str:
    if value is None:
        return "NULL"
    return "TRUE" if value else "FALSE"


async def get_inbox(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = 100,
    before: ARGBefore = None,
    show_active_projects: bool | None = None,
    show_active_messages: bool | None = True,
    show_unread_messages: bool | None = None,
) -> ActivitiesConnection:
    sql_conditions = []

    #
    # Pagination
    #

    user = info.context["user"]

    order_by = ["created_at", "creation_order"]
    paging_fields = FieldInfo(info, ["inbox"])
    need_cursor = paging_fields.has_any(
        "inbox.pageInfo.startCursor",
        "inbox.pageInfo.endCursor",
        "inbox.edges.cursor",
    )

    pagination, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
        need_cursor=need_cursor,
    )
    sql_conditions.extend(paging_conds)

    #
    # Build the query
    #

    query = f"""
        SELECT {cursor}, *
        FROM get_user_inbox(
            '{user.name}',
            {bool2sql(show_active_projects)},
            {bool2sql(show_active_messages)},
            {bool2sql(show_unread_messages)}
        )
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    print(query)

    #
    # Execute the query
    #

    return await resolve(
        ActivitiesConnection,
        ActivityEdge,
        ActivityNode,
        None,
        query,
        first,
        last,
        context=info.context,
    )
