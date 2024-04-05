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
from ayon_server.types import validate_name_list
from ayon_server.utils import SQLTool


async def get_activities(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    activity_types: list[str] | None = None,
    reference_types: list[str] | None = None,
) -> ActivitiesConnection:
    project_name = root.project_name

    sql_conditions = []

    if activity_types is not None:
        validate_name_list(activity_types)
        sql_conditions.append(f"activity_type IN {SQLTool.array(activity_types)}")

    if not (entity_type and entity_id):
        reference_types = ["origin"]

    if reference_types is not None:
        validate_name_list(reference_types)
        sql_conditions.append(f"reference_types IN {SQLTool.array(reference_types)}")

    #
    # Pagination
    #

    order_by = ["activities.created_at", "activitity.creation_order"]
    paging_fields = FieldInfo(info, ["activities"])
    need_cursor = paging_fields.has_any(
        "activities.pageInfo.startCursor",
        "activities.pageInfo.endCursor",
        "activities.edges.cursor",
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
        FROM project_{project_name}.activity_feed
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    #
    # Execute the query
    #

    return await resolve(
        ActivitiesConnection,
        ActivityEdge,
        ActivityNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )
