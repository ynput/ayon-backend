from typing import Annotated

from strawberry.types import Info

from ayon_server.graphql.connections import EventsConnection
from ayon_server.graphql.edges import EventEdge
from ayon_server.graphql.nodes.event import EventNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from ayon_server.types import validate_name_list, validate_user_name_list
from ayon_server.utils import SQLTool


async def get_events(
    root,
    info: Info,
    topics: Annotated[list[str] | None, argdesc("List of topics")] = None,
    projects: Annotated[list[str] | None, argdesc("List of projects")] = None,
    users: Annotated[list[str] | None, argdesc("List of users")] = None,
    states: Annotated[list[str] | None, argdesc("List of states")] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> EventsConnection:
    """Return a list of events."""

    sql_conditions = []

    if topics:
        validate_name_list(topics)
        sql_conditions.append(f"topic IN {SQLTool.array(topics)}")
    if projects:
        validate_name_list(projects)
        sql_conditions.append(f"project_name IN {SQLTool.array(projects)}")
    if users:
        validate_user_name_list(users)
        sql_conditions.append(f"user_name IN {SQLTool.array(users)}")
    if states:
        validate_name_list(states)
        sql_conditions.append(f"status IN {SQLTool.array(states)}")

    order_by = "creation_order"
    pagination, paging_conds = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )
    sql_conditions.extend(paging_conds)

    query = f"""
        SELECT * FROM events
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        EventsConnection,
        EventEdge,
        EventNode,
        None,
        query,
        first,
        last,
        context=info.context,
        order_by="updated_at",
    )
