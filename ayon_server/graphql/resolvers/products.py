from typing import Annotated

from ayon_server.access.utils import folder_access_list
from ayon_server.graphql.connections import ProductsConnection
from ayon_server.graphql.edges import ProductEdge
from ayon_server.graphql.nodes.product import ProductNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    FieldInfo,
    argdesc,
    create_pagination,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.graphql.types import Info
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool

SORT_OPTIONS = {
    "name": "products.name",
    "productType": "products.product_type",
    "createdAt": "products.created_at",
    "updatedAt": "products.updated_at",
}


async def get_products(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    folder_ids: Annotated[
        list[str] | None, argdesc("List of parent folder IDs to filter by")
    ] = None,
    names: Annotated[list[str] | None, argdesc("Filter by a list of names")] = None,
    names_ci: Annotated[
        list[str] | None, argdesc("Filter by a list of names (case insensitive)")
    ] = None,
    name_ex: Annotated[
        str | None, argdesc("Match product names by a regular expression")
    ] = None,
    path_ex: Annotated[
        str | None, argdesc("Match product by a regex of the parent folder path regex")
    ] = None,
    product_types: Annotated[
        list[str] | None, argdesc("List of product types to filter by")
    ] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> ProductsConnection:
    """Return a list of products."""

    project_name = root.project_name
    fields = FieldInfo(info, ["products.edges.node", "product"])

    #
    # SQL
    #

    sql_columns = [
        "products.id AS id",
        "products.name AS name",
        "products.folder_id AS folder_id",
        "products.product_type AS product_type",
        "products.attrib AS attrib",
        "products.data AS data",
        "products.status AS status",
        "products.tags AS tags",
        "products.active AS active",
        "products.created_at AS created_at",
        "products.updated_at AS updated_at",
        "products.creation_order AS creation_order",
    ]
    sql_conditions = []
    sql_joins = []

    if ids is not None:
        if not ids:
            return ProductsConnection()
        sql_conditions.append(f"products.id IN {SQLTool.id_array(ids)}")

    if folder_ids is not None:
        if not folder_ids:
            return ProductsConnection()
        sql_conditions.append(f"products.folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"products.folder_id = '{root.id}'")

    if names is not None:
        if not names:
            return ProductsConnection()
        validate_name_list(names)
        sql_conditions.append(f"products.name IN {SQLTool.array(names)}")

    if names_ci is not None:
        if not names_ci:
            return ProductsConnection()
        validate_name_list(names_ci)
        names_ci = [name.lower() for name in names_ci]
        sql_conditions.append(f"LOWER(products.name) IN {SQLTool.array(names_ci)}")

    if product_types is not None:
        if not product_types:
            return ProductsConnection()
        validate_name_list(product_types)
        sql_conditions.append(
            f"products.product_type IN {SQLTool.array(product_types)}"
        )

    if statuses is not None:
        if not statuses:
            return ProductsConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")
    if tags is not None:
        if not tags:
            return ProductsConnection()
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "products.id", has_links)
        )

    if name_ex is not None:
        sql_conditions.append(f"products.name ~ '{name_ex}'")

    if path_ex is not None:
        # TODO: sanitize
        sql_conditions.append(f"'/' || hierarchy.path ~ '{path_ex}'")

    access_list = None
    if root.__class__.__name__ == "ProjectNode":
        # Selecting products directly from the project node,
        # so we need to check access rights
        user = info.context["user"]
        access_list = await folder_access_list(user, project_name)
        if access_list is not None:
            sql_conditions.append(
                f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
            )

    #
    # Join with folders if parent folder is requested
    #

    if "folder" in fields or (access_list is not None) or (path_ex is not None):
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.label AS _folder_label",
                "folders.folder_type AS _folder_folder_type",
                "folders.parent_id AS _folder_parent_id",
                "folders.thumbnail_id AS _folder_thumbnail_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.status AS _folder_status",
                "folders.tags AS _folder_tags",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
            ]
        )
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = products.folder_id
            """
        )

        if any(field.endswith("folder.attrib") for field in fields):
            sql_columns.extend(
                [
                    "pr.attrib as _folder_project_attributes",
                    "ex.attrib as _folder_inherited_attributes",
                ]
            )
            sql_joins.extend(
                [
                    f"""
                    LEFT JOIN project_{project_name}.exported_attributes AS ex
                    ON folders.parent_id = ex.folder_id
                    """,
                    f"""
                    INNER JOIN public.projects AS pr
                    ON pr.name ILIKE '{project_name}'
                    """,
                ]
            )
        else:
            sql_columns.extend(
                [
                    "'{}'::JSONB as _folder_project_attributes",
                    "'{}'::JSONB as _folder_inherited_attributes",
                ]
            )

        if any(
            field.endswith("folder.path")
            or field.endswith("folder.parents")
            or (path_ex is not None)
            for field in fields
        ) or (access_list is not None):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON folders.id = hierarchy.id
                """
            )

    #
    # Verison_list
    #

    if "versionList" in fields:
        sql_columns.extend(
            ["version_list.ids as version_ids", "version_list.versions as version_list"]
        )
        sql_joins.append(
            f"""
            LEFT JOIN
                project_{project_name}.version_list
                ON products.id = version_list.product_id
            """
        )

    #
    # Pagination
    #

    order_by = ["products.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"products.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    paging_fields = FieldInfo(info, ["products"])
    need_cursor = paging_fields.has_any(
        "products.pageInfo.startCursor",
        "products.pageInfo.endCursor",
        "products.edges.cursor",
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
    # Query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.products
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        ProductsConnection,
        ProductEdge,
        ProductNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_product(root, info: Info, id: str) -> ProductNode | None:
    """Return a representation node based on its ID"""
    if not id:
        return None
    connection = await get_products(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
