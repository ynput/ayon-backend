from datetime import datetime

from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.entities import ProjectEntity
from ayon_server.graphql.connections import ActivitiesConnection
from ayon_server.graphql.edges import ActivityEdge
from ayon_server.graphql.nodes.activity import ActivityNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
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
    activity_ids: list[str] | None = None,
    tags: list[str] | None = None,
    categories: list[str | None] | None = None,
    changed_before: str | None = None,
    changed_after: str | None = None,
) -> ActivitiesConnection:
    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    info.context["project"] = project

    # Ensure the guest user is allowed in this project

    user = info.context["user"]
    if user.is_guest:
        if user.attrib.email not in project.data.get("guestUsers", {}):
            raise Exception("Guest user not allowed in this project")

    # load activity categories and push them to context as
    # a dictionary for easy access

    activity_categories = await ActivityCategories.get_activity_categories(project_name)
    info.context["activity_categories"] = {}
    for cat in activity_categories:
        info.context["activity_categories"][cat["name"]] = {
            "color": cat.get("color"),
            "name": cat.get("name"),
        }

    # SQL components

    sql_cte = []
    sql_joins = []
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
        elif activity_ids:
            pass
        else:
            reference_types = reference_types or ["origin"]

    if activity_ids is not None:
        sql_conditions.append(f"activity_id IN {SQLTool.id_array(activity_ids)}")

    if changed_before:
        # ensure the date is a valid ISO 8601 datetime
        changed_before_dt = datetime.fromisoformat(changed_before)
        sql_conditions.append(f"updated_at < '{changed_before_dt.isoformat()}'")

    if changed_after:
        # ensure the date is a valid ISO 8601 datetime
        changed_after_dt = datetime.fromisoformat(changed_after)
        sql_conditions.append(f"updated_at > '{changed_after_dt.isoformat()}'")

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

    if tags:
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if user.is_guest:
        # guest users can only see activities that are tagged with
        # entityList they have access to AND the category matches
        # one of the categories that are allowed to access (or NULL)

        # allowed categories are stored in powerpack addon settings
        # this is different from guestCommentCategory, that is stored per list
        # in entityList.data and is used to determine whether user CAN comment
        # and with which category

        accessible_categories = await ActivityCategories.get_accessible_categories(
            user,
            project=project,
        )

        sql_cte.append(
            f"""
            accessible_lists AS (
                SELECT id, data FROM project_{project_name}.entity_lists
                WHERE COALESCE((access->'guest:{user.attrib.email}')::INTEGER, 0) > 0
            )
            """
        )

        sql_joins.append(
            f"""
            JOIN accessible_lists ON
                (activity_data->>'entityList')::UUID = accessible_lists.id
            AND (
                activity_data->>'category' IS NULL
                OR activity_data->>'category' = ANY({
                    SQLTool.array(accessible_categories, curly=True)
                })
            )
            """
        )
    elif not user.is_manager:
        # normal users can see activities that match their readable categories
        accessible_categories = await ActivityCategories.get_accessible_categories(
            user,
            project=project,
        )
        if accessible_categories:
            sql_conditions.append(
                f"""
                (
                    activity_data->>'category' IS NULL
                    OR activity_data->>'category' = ANY({
                        SQLTool.array(accessible_categories, curly=True)
                    })
                )
                """
            )
        else:
            # user has no access to any categories,
            # so can see only activities without category
            sql_conditions.append("activity_data->>'category' IS NULL")

    if categories:
        cat_conds = []
        if None in categories:
            cat_conds.append("activity_data->>'category' IS NULL")
        cats = [c for c in categories if c is not None]
        if cats:
            cat_conds.append(f"activity_data->>'category' IN {SQLTool.array(cats)}")
        sql_conditions.append(f"({SQLTool.conditions(cat_conds, 'OR', False)})")

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
    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )
    sql_conditions.append(paging_conds)

    #
    # Build the query
    #

    if sql_cte:
        cte = ", ".join(sql_cte)
        cte = f"WITH {cte}"
    else:
        cte = ""

    query = f"""
        {cte}
        SELECT {cursor}, *
        FROM project_{project_name}.activity_feed
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    # Keep this here for future debugging
    # from ayon_server.logging import logger
    #
    # logger.trace(f"Querying activities: {query}")

    return await resolve(
        ActivitiesConnection,
        ActivityEdge,
        ActivityNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        context=info.context,
        order_by=order_by,
    )
