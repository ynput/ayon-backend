from base64 import b64decode

from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.edges import ActivityEdge
from ayon_server.graphql.nodes.activity import ActivityNode
from ayon_server.graphql.resolvers.common import (
    ARGBefore,
    ARGLast,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.utils import SQLTool, json_loads


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
    if user.is_guest:
        return ActivitiesConnection(edges=[])
    elif not user.is_manager:
        # create a map, of {project_name: list of accessible categories}
        # that will be populated (and used) in the resolve function
        # to filter out inaccessible activities
        info.context["inboxAccessibleCategories"] = {}

    sql_conditions = []
    subquery_conds = []

    if show_important_messages is not None:
        # double escape the quotes, because we are in a string
        # that is passed as an argument to funcition, which uses
        # it to format a string... i am so sorry
        operator = "IN" if show_important_messages else "NOT IN"
        if show_important_messages:
            not_important = "AND t.activity_type != ''status.change''"
        else:
            not_important = "OR t.activity_type = ''status.change''"
        subquery_conds.append(
            f"(t.reference_type {operator} (''mention'', ''watching'') {not_important})"
        )

    subquery_add_arg = ""
    if subquery_conds:
        subquery_add_arg = f"AND {SQLTool.conditions(subquery_conds, add_where=False)}"

    #
    # Build the query
    #

    order_by = [
        "updated_at",
        "creation_order",
    ]

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first=None,
        after=None,
        last=last,
        before=before,
    )

    sql_conditions.append(paging_conds)

    if before:
        try:
            cur_data = json_loads(b64decode(before).decode())
            bf = f"'{cur_data[0]}'::timestamptz"
        except Exception:
            bf = "NULL"
    else:
        bf = "NULL"

    buffer_size = 1000  # last

    query = f"""
        SELECT {cursor}, *
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
        {ordering}
    """

    #
    # Execute the query
    #

    # start_time = time.monotonic()
    info.context["inbox"] = True
    res = await resolve(
        ActivitiesConnection,
        ActivityEdge,
        ActivityNode,
        query,
        last=last,
        order_by=order_by,
        context=info.context,
    )
    # end_time = time.monotonic()
    return res
