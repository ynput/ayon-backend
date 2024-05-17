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
    entity_ids: list[str] | None = None,
    entity_names: list[str] | None = None,
    activity_types: list[str] | None = None,
    reference_types: list[str] | None = None,
) -> ActivitiesConnection:
    project_name = root.project_name

    sql_conditions = []

    if not (entity_type and entity_ids):
        if root.__class__.__name__ == "FolderNode":
            entity_type = "folder"
            entity_ids = [root.id]
        elif root.__class__.__name__ == "ProductNode":
            entity_type = "product"
            entity_ids = [root.id]
        elif root.__class__.__name__ == "VersionNode":
            entity_type = "version"
            entity_ids = [root.id]
        elif root.__class__.__name__ == "TaskNode":
            entity_type = "task"
            entity_ids = [root.id]
        elif root.__class__.__name__ == "WorkfileNode":
            entity_type = "workfile"
            entity_ids = [root.id]
        elif root.__class__.__name__ == "RepresentationNode":
            entity_type = "representation"
            entity_ids = [root.id]
        else:
            reference_types = reference_types or ["origin"]

    if activity_types is not None:
        validate_name_list(activity_types)

        if "checklist" in activity_types:
            if "comment" not in activity_types:
                # comments include checklist items so we don't need to query both
                sql_conditions.append(
                    """(
                        activity_type = 'comment'
                        AND activity_data->>'hasChecklist' IS NOT NULL
                    )"""
                )
            activity_types.remove("checklist")

        if activity_types:
            sql_conditions.append(f"activity_type IN {SQLTool.array(activity_types)}")

    if reference_types is not None:
        validate_name_list(reference_types)
        sql_conditions.append(f"reference_type IN {SQLTool.array(reference_types)}")

    if entity_ids is not None:
        sql_conditions.append(f"entity_id IN {SQLTool.array(entity_ids)}")
        # do not list mentions on the same entity
        # FIXME
        # sql_conditions.append(
        #     f"""
        #     (
        #         reference_type != 'origin'
        #         AND reference_id IN {SQLTool.array(entity_ids)}
        #     )
        #     """
        # )
    if entity_names is not None:
        validate_name_list(entity_names)
        sql_conditions.append(f"entity_name IN {SQLTool.array(entity_names)}")

    #
    # Pagination
    #

    order_by = ["created_at", "creation_order"]
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
