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
from openpype.utils import SQLTool, validate_name


async def get_events(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> EventsConnection:
    """Return a list of events."""

    query = f"""
        SELECT * FROM events
        ORDER BY updated_at DESC
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
