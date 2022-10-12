from typing import Annotated

from strawberry.types import Info

from openpype.graphql.connections import EventsConnection
from openpype.graphql.edges import EventEdge
from openpype.graphql.nodes.event import EventNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from openpype.utils import SQLTool


async def get_events(
    root,
    info: Info,
    topics: Annotated[list[str] | None, argdesc("List of topics")] = None,
    projects: Annotated[list[str] | None, argdesc("List of projects")] = None,
    users: Annotated[list[str] | None, argdesc("List of users")] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> EventsConnection:
    """Return a list of events."""

    sql_conditions = []

    if topics:
        sql_conditions.append(f"topic IN {SQLTool.array(topics)}")
    if projects:
        sql_conditions.append(f"project_name IN {SQLTool.array(projects)}")
    if users:
        sql_conditions.append(f"user_name IN {SQLTool.array(users)}")

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
