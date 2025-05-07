import functools
from typing import Any

from ayon_server.access.utils import AccessChecker
from ayon_server.entities.models.fields import (
    folder_fields,
    product_fields,
    representation_fields,
    task_fields,
    version_fields,
    workfile_fields,
)
from ayon_server.exceptions import (
    BadRequestException,
    NotImplementedException,
)
from ayon_server.graphql.nodes.entity_list import (
    EntityListItemEdge,
    EntityListItemsConnection,
    EntityListNode,
)
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    create_folder_access_list,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import (
    create_pagination,
    get_attrib_sort_case,
)
from ayon_server.graphql.types import Info
from ayon_server.utils import SQLTool

COLS_ITEMS = [
    "id",
    "entity_id",
    "entity_list_id",
    "position",
    "label",
    "attrib",
    "data",
    "tags",
    "folder_path",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
]


COLS_COMMON = [
    "id",
    "attrib",
    "data",
    "active",
    "status",
    "tags",
    "created_at",
    "updated_at",
]


ITEM_SORT_OPTIONS = {
    "position": "i.position",
    "label": "i.label",
    "createdAt": "i.created_at",
    "updatedAt": "i.updated_at",
    "createdBy": "i.created_by",
    "updatedBy": "i.updated_by",
    "folderPath": "i.folder_path",
}


@functools.cache
def cols_for_entity(entity_type: str) -> list[str]:
    fields: list[Any]
    if entity_type == "folder":
        fields = folder_fields
    elif entity_type == "task":
        fields = task_fields
    elif entity_type == "product":
        fields = product_fields
    elif entity_type == "version":
        fields = version_fields
    elif entity_type == "representation":
        fields = representation_fields
    elif entity_type == "workfile":
        fields = workfile_fields
    else:
        # this cannot happen, but let's be safe
        raise NotImplementedException(
            f"Entity lists with {entity_type} are not supported"
        )
    return COLS_COMMON + [
        field["name"]
        for field in fields
        if field["name"] not in COLS_COMMON and not field.get("dynamic")
    ]


async def build_entity_sorting(sort_by: str, entity_type: str) -> str:
    if sort_by in ["data"]:
        # This won't be supported, because it doesn't make sense
        raise NotImplementedException(f"Unable to sort by entity.{sort_by}")

    if sort_by.startswith("attrib."):
        attr_name = sort_by[7:]
        exp = "e.attrib"
        if entity_type == "folder":
            exp = "(pr.attrib || pf.attrib || e.attrib)"
        elif entity_type == "task":
            exp = "(pf.attrib || e.attrib)"
        attr_case = await get_attrib_sort_case(attr_name, exp)
        return f"({attr_case})"

    cols = cols_for_entity(entity_type)
    if sort_by not in cols:
        raise BadRequestException(f"Invalid sort key entity.{sort_by}")
    return f"e.{sort_by}"


async def get_entity_list_items(
    root: EntityListNode,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    sort_by: str | None = None,
    filter: str | None = None,
    accessible_only: bool = False,
) -> EntityListItemsConnection:
    project_name = root.project_name
    entity_type = root.entity_type

    # Ensure we're not querying multiple entity types
    # and store the entity type in the context;
    # We need it in the edge to create the node

    if orig_et := info.context.get("entity_type"):
        if orig_et != entity_type:
            raise BadRequestException(
                "Queried multiple entity types in the same query. "
                "This is not supported (and will not be)."
            )
    else:
        info.context["entity_type"] = entity_type

    #
    # entity_list_items columns
    #

    sql_joins = []
    sql_columns = [f"i.{col} {col}" for col in COLS_ITEMS]
    sql_conditions = [f"entity_list_id = '{root.id}'"]

    # Entity access control
    #
    # There are two options for preventing users to access underlying entities,
    # if they don't have access to them:
    #
    #  - When `accessible_only` is set to True, we will only return items that
    #    are accessible to the user. This is done by filtering the items on the
    #    SQL level. For this method, we need folder_access_list
    #
    #  - When `accessible_only` is set to False, we will return all items,
    #    including the item metadata, but node will be set to null.
    #    This is implemented on EntityListItemEdge level and we need access_checker
    #    to do that.

    if accessible_only:
        access_list = await create_folder_access_list(root, info)
        if access_list is not None:
            # if access list is None, user has access to everything within the project
            # so we don't need to filter anything

            sql_conditions.append(
                f"i.folder_path ILIKE ANY  ('{{ {','.join(access_list)} }}')"
            )

    elif "access_checker" not in info.context:
        # Push access checker to the context, so it is available for all item edges
        access_checker = AccessChecker()
        await access_checker.load(info.context["user"], project_name, "read")
        info.context["access_checker"] = access_checker

    #
    # Join with the actual entity
    #

    cols = cols_for_entity(entity_type)

    sql_joins.append(
        f"""
        INNER JOIN project_{project_name}.{entity_type}s e
        ON e.id = i.entity_id
        """
    )
    for col in cols:
        sql_columns.append(f"e.{col} as _entity_{col}")

    # Unified attributes
    # Create additions column
    # if entity_type == "folder":
    #     s

    # Special cases:

    if entity_type == "task":
        # when querying tasks, we need the parent folder attributes
        # as well because of the inheritance
        sql_columns.append("pf.attrib as _entity_parent_folder_attrib")
        sql_joins.append(
            f"INNER JOIN project_{project_name}.exported_attributes AS pf "
            "ON e.folder_id = pf.folder_id\n"
        )

    elif entity_type == "folder":
        # when querying folders, we need the parent folder attributes
        # and also the project attribute in the case of root folders
        # ... yeah. and also the hierarchy path
        sql_columns.extend(
            [
                "pf.attrib as _entity_inherited_attributes",
                "pr.attrib as _entity_project_attributes",
                "hierarchy.path AS _entity_path",
            ]
        )
        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.exported_attributes AS pf
                ON e.parent_id = pf.folder_id
                """,
                f"""
                INNER JOIN public.projects AS pr
                ON pr.name ILIKE '{project_name}'
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON e.id = hierarchy.id
                """,
            ]
        )

    # The rest of the entity types should work out of the box

    #
    # Sorting
    #

    order_by = []

    if sort_by:
        if item_sort_by := ITEM_SORT_OPTIONS.get(sort_by):
            order_by.append(item_sort_by)

        if sort_by.startswith("attrib."):
            # TODO
            raise NotImplementedException(
                "Sorting by item attributes is not supported. Yet."
            )

        if sort_by.startswith("entity."):
            order_by.append(await build_entity_sorting(sort_by[7:], entity_type))

    # secondary sorting for duplicate values
    # unless we're already sorting by position

    if sort_by != "position":
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
        SELECT {cursor},
        {", ".join(sql_columns)}
        FROM project_{project_name}.entity_list_items i
        {"".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    from ayon_server.logging import logger

    logger.debug(f"Entity list items query: {query}")

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
