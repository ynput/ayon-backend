from ayon_server.exceptions import NotFoundException, NotImplementedException
from ayon_server.graphql.nodes.entity_list import (
    EntityListItemEdge,
    EntityListItemsConnection,
)
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool

COLS_COMMON = [
    "id",
    "attrib",
    "status",
    "attrib",
    "data",
    "active",
    "tags",
    "created_at",
    "updated_at",
]


COLS_VERSIONS = [
    *COLS_COMMON,
    "version",
    "product_id",
    "task_id",
    "thumbnail_id",
    "author",
]

COL_MAP = {"version": COLS_VERSIONS}


async def get_entity_list_items(
    root,
    info: Info,
    entity_list_id: str,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    sort_by: str | None = None,
) -> EntityListItemsConnection:
    project_name = root.project_name

    #
    # First, fetch the list information
    #

    q = f"""
        SELECT entity_type, access
        FROM project_{project_name}.entity_lists
        WHERE id = $1
    """
    res = await Postgres.fetchrow(q, entity_list_id)
    if not res:
        raise NotFoundException(f"Entity list with id {entity_list_id} not found")
    entity_type = res["entity_type"]
    access = res["access"]
    info.context["entity_type"] = entity_type

    if access:
        # TODO: Implement list ACL check here
        pass

    #
    # entity_list_items columns
    #

    sql_joins = []
    sql_columns = [
        "i.id id",
        "i.entity_id entity_id",
        "i.entity_list_id entity_list_id",
        "i.position position",
        "i.label label",
        "i.attrib attrib",
        "i.data data",
        "i.tags tags",
        "i.folder_path folder_path",
        "i.created_at created_at",
        "i.updated_at updated_at",
        "i.created_by created_by",
        "i.updated_by updated_by",
    ]
    sql_conditions = [f"entity_list_id = '{entity_list_id}'"]
    order_by = []

    #
    # Join with the actual entity
    #

    COLS = COL_MAP.get(entity_type)
    if not COLS:
        raise NotImplementedException(
            f"Entity lists with {entity_type} are not supported"
        )

    sql_joins.append(
        f"""
        INNER JOIN project_{project_name}.{entity_type}s e
        ON e.id = i.entity_id
        """
    )
    for col in COLS:
        sql_columns.append(f"e.{col} as _entity_{col}")

    if f"entity.{sort_by}" in COLS:
        order_by.append(f"e.{sort_by}")

    #
    # Sorting
    #

    if (not order_by) and sort_by:
        if sort_by.startswith("entity.attrib."):
            order_by.append(f"e.attrib ->> '{sort_by[14:]}'")
        elif sort_by.startswith("attrib."):
            order_by.append(f"i.attrib ->> '{sort_by[6:]}'")

    if not order_by:
        order_by.append("i.position")

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )

    sql_conditions.append(paging_conds)

    #
    # Construct the query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.entity_list_items i
        {"".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    # TODO: Remove before merging :)

    from ayon_server.logging import logger

    logger.info(f"QUERY {query}")

    return await resolve(
        EntityListItemsConnection,
        EntityListItemEdge,
        None,
        query,
        project_name=project_name,
        first=first,
        last=last,
        context=info.context,
        order_by=order_by,
    )
