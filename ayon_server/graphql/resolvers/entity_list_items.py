import functools
import json
from typing import Any

from graphql.pyutils import camel_to_snake

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
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.utils import SQLTool

from .common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    FieldInfo,
    create_folder_access_list,
    resolve,
)
from .pagination import create_pagination
from .sorting import get_attrib_sort_case

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
    "position": "position",
    "label": "label",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "createdBy": "created_by",
    "updatedBy": "updated_by",
    "folderPath": "folder_path",
    "path": "folder_path",
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

    # Get attribute definition for the entity list
    attrs = root._data.get("attributes") or []
    info.context["list_attributes"] = {
        attr["name"]: attr["data"].get("type", "string") for attr in attrs
    }

    fields = FieldInfo(info, None)

    #
    # entity_list_items columns
    #

    sql_cte = []
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

    if info.context["user"].is_guest:
        # Guest users can access underlying entities as long they have
        # access to the entity list itself, so we don't need to do anything
        pass

    elif accessible_only:
        access_list = await create_folder_access_list(root, info)
        if access_list is not None:
            # if access list is None, user has access to everything within the project
            # so we don't need to filter anything

            sql_conditions.append(
                f"folder_path ILIKE ANY  ('{{ {','.join(access_list)} }}')"
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

    # Special cases:

    allowed_parent_keys = []

    if entity_type == "task":
        if fields.any_endswith("hasReviewables"):
            sql_cte.append(
                f"""
                reviewables AS (
                    SELECT v.task_id AS entity_id
                    FROM project_{project_name}.activity_feed af
                    INNER JOIN project_{project_name}.versions v
                    ON af.entity_id = v.id
                    AND af.entity_type = 'version'
                    AND af.activity_type = 'reviewable'
                )
                """
            )

            sql_columns.append(
                """
                EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = e.id
                ) AS _entity_has_reviewables
                """
            )

        # when querying tasks, we need the parent folder attributes
        # as well because of the inheritance
        sql_columns.append("px.attrib as _entity_parent_folder_attrib")
        sql_columns.append("pf.folder_type as _parent_folder_type")
        sql_columns.append("hierarchy.path AS _entity__folder_path")
        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.exported_attributes AS px
                ON e.folder_id = px.folder_id
                """,
                f"""
                INNER JOIN project_{project_name}.folders AS pf
                ON e.folder_id = pf.id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON e.folder_id = hierarchy.id
                """,
            ]
        )
        allowed_parent_keys = ["folder_type"]

    elif entity_type == "folder":
        if fields.any_endswith("hasReviewables"):
            sql_cte.append(
                f"""
                reviewables AS (
                    SELECT p.folder_id AS entity_id
                    FROM project_{project_name}.activity_feed af
                    INNER JOIN project_{project_name}.versions v
                    ON af.entity_id = v.id
                    AND af.entity_type = 'version'
                    AND  af.activity_type = 'reviewable'
                    INNER JOIN project_{project_name}.products p
                    ON p.id = v.product_id
                )
                """
            )

            sql_columns.append(
                """
                EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = e.id
                ) AS _entity_has_reviewables
                """
            )

        # when querying folders, we need the parent folder attributes
        # and also the project attribute in the case of root folders
        # ... yeah. and also the hierarchy path
        sql_columns.extend(
            [
                "px.attrib AS _entity_inherited_attributes",
                "pr.attrib AS _entity_project_attributes",
                "pf.folder_type AS _parent_folder_type",
                "hierarchy.path AS _entity_path",
            ]
        )
        sql_joins.extend(
            [
                f"""
                LEFT JOIN project_{project_name}.exported_attributes AS px
                ON e.parent_id = px.folder_id
                """,
                f"""
                LEFT JOIN project_{project_name}.folders AS pf
                ON e.parent_id = pf.id
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
        allowed_parent_keys = ["folder_type"]

    elif entity_type == "product":
        sql_columns.extend(
            [
                "pf.folder_type as _parent_folder_type",
                "hierarchy.path AS _entity__folder_path",
            ]
        )
        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.folders AS pf
                ON e.folder_id = pf.id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON e.folder_id = hierarchy.id
                """,
            ]
        )
        allowed_parent_keys = ["folder_type"]

    elif entity_type == "version":
        sql_columns.extend(
            [
                "pf.folder_type as _parent_folder_type",
                "pd.product_type as _parent_product_type",
                "pt.task_type as _parent_task_type",
                "hierarchy.path AS _entity__folder_path",
                "pd.name AS _entity__product_name",
            ]
        )
        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.products AS pd
                ON e.product_id = pd.id
                """,
                f"""
                INNER JOIN project_{project_name}.folders AS pf
                ON pd.folder_id = pf.id
                """,
                f"""
                LEFT JOIN project_{project_name}.tasks AS pt
                ON e.task_id = pt.id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON pd.folder_id = hierarchy.id
                """,
            ]
        )
        allowed_parent_keys = ["folder_type", "product_type", "task_type"]

        # For versions, we also need hasReviewables
        if fields.any_endswith("hasReviewables"):
            sql_cte.append(
                f"""
                reviewables AS (
                    SELECT entity_id FROM project_{project_name}.activity_feed
                    WHERE entity_type = 'version'
                    AND   activity_type = 'reviewable'
                )
                """
            )

            sql_columns.append(
                """
                EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = e.id
                ) AS _entity_has_reviewables
                """
            )

    # Unified attributes
    # Create additions column _all_attrib that contains all attributes
    # from the entity and the item itself - used for sorting and filtering

    if entity_type == "folder":
        sql_columns.append(
            "(pr.attrib || COALESCE(px.attrib, '{}'::JSONB) || e.attrib || i.attrib) as _all_attrib"  # noqa: E501
        )
    elif entity_type == "task":
        sql_columns.append(
            "(COALESCE(px.attrib, '{}'::JSONB) || e.attrib || i.attrib) as _all_attrib"
        )  # noqa: E501
    else:
        sql_columns.append("(e.attrib || i.attrib) as _all_attrib")

    #
    # Sorting
    #

    order_by = []

    if sort_by:
        if item_sort_by := ITEM_SORT_OPTIONS.get(sort_by):
            order_by.append(item_sort_by)

        elif sort_by in ITEM_SORT_OPTIONS.values():
            order_by.append(sort_by)

        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            attr_case = await get_attrib_sort_case(attr_name, "_all_attrib")
            order_by.append(f"({attr_case})")

        elif sort_by.startswith("entity"):
            s = camel_to_snake(sort_by)
            s = s.removeprefix("entity_")
            if s not in cols:
                raise BadRequestException(
                    f"Invalid entity sort key {sort_by}. "
                    f"Available are: {', '.join(cols)}"
                )
            order_by.append(f"_entity_{s}")

        elif sort_by.startswith("parent"):
            s = camel_to_snake(sort_by)
            s = s.removeprefix("parent_")
            if s not in allowed_parent_keys:
                raise BadRequestException(
                    f"Invalid parent sort key {s}. "
                    f"Available are: {', '.join(allowed_parent_keys)}"
                )
            order_by.append(f"_parent_{s}")

        else:
            # This is not a valid sort key
            raise BadRequestException(f"Invalid sort key {sort_by}")

    # secondary sorting for duplicate values
    # unless we're already sorting by position

    if sort_by != "position":
        order_by.append("position")

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )

    sql_conditions.append(paging_conds)

    #
    # Filtering
    #

    if filter:
        column_whitelist = [
            *COLS_ITEMS,
            *[f"entity_{col}" for col in cols],
            *[f"parent_{col}" for col in allowed_parent_keys],
        ]

        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        try:
            filter = build_filter(
                fq,
                column_whitelist=column_whitelist,
                column_map={
                    "attrib": "_all_attrib",
                    **{f"entity_{col}": f"_entity_{col}" for col in cols},
                    **{
                        f"parent_{col}": f"_parent_{col}" for col in allowed_parent_keys
                    },  # noqa: E501
                },
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        if filter is not None:
            sql_conditions.append(filter)

    #
    # Construct the query

    if sql_cte:
        cte = ", ".join(sql_cte)
        cte = f"WITH {cte}"
    else:
        cte = ""

    query = f"""
        {cte}
        SELECT {cursor}, * FROM (
            SELECT
            {", ".join(sql_columns)}

            FROM project_{project_name}.entity_list_items i
            {"".join(sql_joins)}
        ) as sub
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    # from ayon_server.logging import logger
    #
    # logger.debug(f"Entity list items query: {query}")
    #
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
