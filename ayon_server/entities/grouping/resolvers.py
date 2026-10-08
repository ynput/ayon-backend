from typing import TYPE_CHECKING, Literal

from ayon_server.access.utils import folder_access_list
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.anatomy import get_project_anatomy
from ayon_server.helpers.hierarchy_cache import AYON_INTERNAL_FOLDER_NAME
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import SQLTool

from .common import EntityGroup

if TYPE_CHECKING:
    from ayon_server.entities import UserEntity


async def get_status_or_type_groups(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    key: Literal["status", "task_type", "folder_type"],
) -> list[EntityGroup]:
    """Get task groups based on status or entity subtype.

    This works with folder and task entities
    """

    if key == "task_type":
        if entity_type != "task":
            raise ValueError("key 'task_type' can only be used with tasks.")
        join_table = "task_types"
    elif key == "folder_type":
        if entity_type != "folder":
            raise ValueError("key 'folder_type' can only be used with folders.")
        join_table = "folder_types"
    elif key == "status":
        join_table = "statuses"
    else:
        raise ValueError(f"Invalid key: {key}")

    groups: list[EntityGroup] = []

    query = f"""
        WITH counts AS (
            SELECT count(*) AS count, {key} AS value
            FROM project_{project_name}.{entity_type}s
            GROUP BY {key}
        )
        SELECT
            f.name AS value,
            f.data->>'icon' AS icon,
            f.data->>'color' AS color,
            COALESCE(counts.count, 0) AS count
        FROM project_{project_name}.{join_table} f
        LEFT JOIN counts
        ON f.name = counts.value
        AND (f.data->'scope' IS NULL OR f.data->'scope' ? '{entity_type}')
    """
    result = await Postgres.fetch(query)
    for row in result:
        group = EntityGroup(
            value=row["value"],
            label=row["value"],
            icon=row["icon"],
            color=row["color"],
            count=row["count"],
        )
        groups.append(group)
    return groups


async def get_assignees_groups(project_name: str) -> list[EntityGroup]:
    """Get task groups based on assignees."""
    groups: list[EntityGroup] = []

    query = f"""
        WITH all_assignees AS (
            SELECT unnest(assignees) AS assignee
            FROM project_{project_name}.tasks
        ),
        user_counts AS (
            SELECT count(*) AS count, assignee
            FROM all_assignees
            GROUP BY assignee
        )
        SELECT
            users.name AS name,
            users.attrib->>'fullName' AS label,
            COALESCE(user_counts.count, 0) AS count
        FROM public.users users
        LEFT JOIN user_counts
        ON users.name = user_counts.assignee
    """
    result = await Postgres.fetch(query)
    for row in result:
        group = EntityGroup(
            value=row["name"],
            label=row["label"],
            count=row["count"],
        )
        groups.append(group)
    return groups


async def get_attrib_groups(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    key: str,
) -> list[EntityGroup]:
    """Get task groups based on custom attributes."""
    groups: list[EntityGroup] = []

    if not attribute_library.is_valid(entity_type, key):
        raise BadRequestException(f"Invalid {entity_type} attribute {key}")

    attr_config = attribute_library.by_name(key)

    attr_type = attr_config.get("type", "string")
    attr_enum = attr_config.get("enum")

    if attr_type.startswith("list_of"):
        raise NotImplementedError("Grouping by list attributes is not supported.")

    enum_dict = {}
    if attr_enum:
        for item in attr_enum:
            enum_dict[item["value"]] = {
                "label": item.get("label"),
                "icon": item.get("icon"),
                "color": item.get("color"),
            }

    logger.debug(f"Attr config: {attr_config}")
    logger.debug(f"enum_dict: {enum_dict}")

    if entity_type == "task":
        values_cte = f"""
            SELECT
                COALESCE(t.attrib->'{key}', ex.attrib->'{key}') AS value
            FROM project_{project_name}.tasks t
            JOIN project_{project_name}.exported_attributes ex
            ON t.folder_id = ex.folder_id
            WHERE t.attrib ? '{key}' OR ex.attrib ? '{key}'
        """

    elif entity_type == "folder":
        values_cte = f"""
            SELECT
                COALESCE(
                    f.attrib->'{key}',
                    ex.attrib->'{key}',
                    pr.attrib->'key'
                ) AS value
            FROM project_{project_name}.folders f
            JOIN project_{project_name}.exported_attributes ex
            ON f.id = ex.folder_id
            JOIN public.projects pr
            ON pr.name = '{project_name}'
            WHERE f.attrib ? '{key}' OR ex.attrib ? '{key}' OR pr.attrib ? '{key}'
        """
    else:
        values_cte = f"""
            SELECT
                attrib->'{key}' AS value
            FROM project_{project_name}.{entity_type}s
            WHERE attrib ? '{key}'
        """

    query = f"""
        WITH values AS ({values_cte})
        SELECT
            values.value AS value,
            COUNT(*) AS count
        FROM values
        GROUP BY values.value
    """
    result = await Postgres.fetch(query)

    for row in result:
        value = row["value"]
        count = row["count"]

        meta = enum_dict.pop(value, {})

        group = EntityGroup(value=value, count=count, **meta)
        groups.append(group)

    for value, meta in enum_dict.items():
        group = EntityGroup(value=value, **meta, count=0)
        groups.append(group)

    return groups


async def get_tags_groups(
    project_name: str,
    entity_type: ProjectLevelEntityType,
) -> list[EntityGroup]:
    """Get task groups based on tags."""
    groups: list[EntityGroup] = []

    query = f"""
        WITH all_tags AS (
            SELECT unnest(tags) AS tag
            FROM project_{project_name}.{entity_type}s
        ),
        tag_counts AS (
            SELECT count(*) AS count, tag
            FROM all_tags
            GROUP BY tag
        )
        SELECT
            t.name AS value,
            t.data->>'icon' AS icon,
            t.data->>'color' AS color,
            COALESCE(tag_counts.count, 0) AS count
        FROM project_{project_name}.tags t
        LEFT JOIN tag_counts
        ON t.name = tag_counts.tag
    """
    result = await Postgres.fetch(query)
    for row in result:
        group = EntityGroup(
            value=row["value"],
            label=row["value"],
            icon=row["icon"],
            color=row["color"],
            count=row["count"],
        )
        groups.append(group)
    return groups


async def get_folder_groups(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    user: "UserEntity",
) -> list[EntityGroup]:
    """Get entity groups based on the folder the entity belongs to.

    Only folders containing at least one entity of the given type are returned.
    Group value is the folder id, label is the full folder path.
    """

    if entity_type in ("task", "product"):
        counts_cte = f"""
            SELECT folder_id, count(*) AS count
            FROM project_{project_name}.{entity_type}s
            GROUP BY folder_id
        """
    elif entity_type == "version":
        # Pre-aggregate versions per product (index-only scan on product_id)
        # so the join with products is products-sized, not versions-sized.
        counts_cte = f"""
            SELECT p.folder_id, sum(vc.count)::bigint AS count
            FROM (
                SELECT product_id, count(*) AS count
                FROM project_{project_name}.versions
                GROUP BY product_id
            ) vc
            JOIN project_{project_name}.products p
            ON p.id = vc.product_id
            GROUP BY p.folder_id
        """
    else:
        raise BadRequestException(
            "Grouping by folder is only supported for tasks, products and versions."
        )

    conditions = [f"NOT starts_with(h.path, '{AYON_INTERNAL_FOLDER_NAME}')"]
    facl = await folder_access_list(user, project_name, "read")
    if facl is not None:
        conditions.append(f"h.path like ANY ('{{ {','.join(facl)} }}')")

    query = f"""
        WITH counts AS ({counts_cte})
        SELECT
            f.id AS value,
            h.path AS label,
            ft.data->>'icon' AS icon,
            counts.count AS count
        FROM counts
        JOIN project_{project_name}.folders f
        ON f.id = counts.folder_id
        JOIN project_{project_name}.hierarchy h
        ON h.id = f.id
        LEFT JOIN project_{project_name}.folder_types ft
        ON ft.name = f.folder_type
        {SQLTool.conditions(conditions)}
        ORDER BY h.path
    """
    result = await Postgres.fetch(query)
    return [
        EntityGroup(
            value=row["value"],
            label=row["label"],
            icon=row["icon"],
            count=row["count"],
        )
        for row in result
    ]


async def get_product_type_groups(
    project_name: str,
) -> list[EntityGroup]:
    """
    Retrieve product groups based on product types for the given project.

    For each product type, returns a group containing:
        - value: the product type name
        - label: the product type name
        - icon: the icon from the anatomy configuration for this type
        - color: the color from the anatomy configuration for this type
        - count: the number of products of this type

    Icon and color are sourced from the project's anatomy configuration.
    This differs from other grouping functions (e.g., by tags or status)
    by grouping specifically on product type and enriching with anatomy metadata.
    """
    anatomy = await get_project_anatomy(project_name)
    mapping = {}
    for pt in anatomy.product_base_types.definitions:
        mapping[pt.name] = {
            "icon": pt.icon,
            "color": pt.color,
        }

    query = f"""
        SELECT count(*) AS count, product_type AS value
        FROM project_{project_name}.products
        GROUP BY product_type
    """

    result = await Postgres.fetch(query)
    groups = []
    for row in result:
        group = EntityGroup(
            value=row["value"],
            label=row["value"],
            icon=mapping.get(row["value"], {}).get("icon")
            or anatomy.product_base_types.default.icon,
            color=mapping.get(row["value"], {}).get("color")
            or anatomy.product_base_types.default.color,
            count=row["count"],
        )
        groups.append(group)
    return groups


async def get_product_base_type_groups(
    project_name: str,
) -> list[EntityGroup]:
    """
    Retrieve product groups based on product base types for the given project.

    Returns one group per base type defined in the project anatomy
    (with count=0 if unused), plus any orphan base type values present
    in the products table that are not in the anatomy definitions.

    For backwards compatibility with projects not yet fully migrated,
    products with a NULL product_base_type fall back to their product_type.
    """
    anatomy = await get_project_anatomy(project_name)

    query = f"""
        WITH base_types_with_fallback AS (
            SELECT
                COALESCE(product_base_type, product_type) AS product_base_type
            FROM project_{project_name}.products
        )
        SELECT count(*) AS count, product_base_type AS value
        FROM base_types_with_fallback
        GROUP BY product_base_type
    """
    result = await Postgres.fetch(query)
    counts = {row["value"]: row["count"] for row in result}

    groups: list[EntityGroup] = []
    seen: set[str] = set()
    for pt in anatomy.product_base_types.definitions:
        groups.append(
            EntityGroup(
                value=pt.name,
                label=pt.name,
                icon=pt.icon or anatomy.product_base_types.default.icon,
                color=pt.color or anatomy.product_base_types.default.color,
                count=counts.get(pt.name, 0),
            )
        )
        seen.add(pt.name)

    for value, count in counts.items():
        if value in seen:
            continue
        groups.append(
            EntityGroup(
                value=value,
                label=value,
                icon=anatomy.product_base_types.default.icon,
                color=anatomy.product_base_types.default.color,
                count=count,
            )
        )

    return groups
