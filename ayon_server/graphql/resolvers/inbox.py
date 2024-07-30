from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.edges import ActivityEdge
from ayon_server.graphql.nodes.activity import ActivityNode
from ayon_server.graphql.resolvers.common import (
    ARGBefore,
    ARGLast,
    resolve,
)
from ayon_server.graphql.types import Info
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
    user = info.context["user"]

    sql_conditions = []
    subquery_conds = []

    cursor = (
        "extract(epoch from updated_at) || '.' || lpad(creation_order::text, 8, '0')"  # noqa
    )

    if before:
        sql_conditions.append(f"{cursor} < '{before}'")

    if show_important_messages is not None:
        # double escape the quotes, because we are in a string
        # that is passed as an argument to funcition, which uses
        # it to format a string... i am so sorry
        operator = "IN" if show_important_messages else "NOT IN"
        subquery_conds.append(
            f"t.reference_type {operator} (''mention'', ''watching'')"
        )

    subquery_add_arg = ""
    if subquery_conds:
        subquery_add_arg = f"AND {SQLTool.conditions(subquery_conds, add_where=False)}"

    #
    # Build the query
    #

    if before:
        ts = ".".join(before.split(".")[:-1])
        bf = f"to_timestamp({ts})::timestamptz"
    else:
        bf = "NULL"
    buffer_size = 1000  # last

    query = f"""
        SELECT {cursor} AS cursor, *
        FROM get_user_inbox(
            '{user.name}',
            {bool2sql(show_active_projects)},
            {bool2sql(show_active_messages)},
            {bool2sql(show_unread_messages)},
            {bf},
            {buffer_size},
            '{subquery_add_arg}'
        )
        {SQLTool.conditions(sql_conditions)}
        ORDER BY cursor DESC
    """

    #
    # Execute the query
    #

    # start_time = time.monotonic()
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
    # end_time = time.monotonic()
    return res
