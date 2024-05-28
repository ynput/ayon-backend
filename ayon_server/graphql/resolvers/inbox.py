import time

from strawberry.types import Info

from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.edges import ActivityEdge
from ayon_server.graphql.nodes.activity import ActivityNode
from ayon_server.graphql.resolvers.common import (
    ARGBefore,
    ARGLast,
    FieldInfo,
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
    last: ARGLast = 100,
    before: ARGBefore = None,
    show_active_projects: bool | None = None,
    show_active_messages: bool | None = True,
    show_unread_messages: bool | None = None,
    show_important_messages: bool | None = None,
) -> ActivitiesConnection:
    sql_conditions = []

    #
    # Pagination
    #

    user = info.context["user"]

    paging_fields = FieldInfo(info, ["inbox"])
    need_cursor = paging_fields.has_any(
        "inbox.pageInfo.startCursor",
        "inbox.pageInfo.endCursor",
        "inbox.edges.cursor",
    )

    if need_cursor:
        cursor = "updated_at::text || project_name::text || creation_order::text"
    else:
        cursor = "updated_at::text"

    if before:
        sql_conditions.append(f"cursor < '{before}'")

    subquery_conds = []

    if show_important_messages is not None:
        # double escape the quotes, because we are in a string
        # that is passed as an argument to funcition, which uses
        # it to format a string... i am so sorry
        operator = "=" if show_important_messages else "!="
        subquery_conds.append(f"t.reference_type {operator} ''mention''")

    subquery_add_arg = ""
    if subquery_conds:
        subquery_add_arg = f"AND {SQLTool.conditions(subquery_conds, add_where=False)}"

    #
    # Build the query
    #

    bf = f"'{before}'" if before else "NULL"

    query = f"""
        SELECT {cursor} AS cursor, *
        FROM get_user_inbox(
            '{user.name}',
            {bool2sql(show_active_projects)},
            {bool2sql(show_active_messages)},
            {bool2sql(show_unread_messages)},
            {bf},
            {last},
            '{subquery_add_arg}'
        )
        {SQLTool.conditions(sql_conditions)}
        ORDER BY cursor DESC
    """

    #
    # Execute the query
    #

    start_time = time.monotonic()
    res = await resolve(
        ActivitiesConnection,
        ActivityEdge,
        ActivityNode,
        None,
        query,
        None,
        last,
        context=info.context,
    )
    end_time = time.monotonic()
    print(f"get_inbox: {len(res.edges)} rows in {end_time-start_time:.03f} seconds")
    return res
