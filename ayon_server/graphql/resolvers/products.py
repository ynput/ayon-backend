import json
from typing import Annotated

from ayon_server.access.utils import folder_access_list
from ayon_server.exceptions import BadRequestException, NotFoundException
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
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import (
    validate_name_list,
    validate_status_list,
    validate_type_name_list,
)
from ayon_server.utils import SQLTool, slugify

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
    has_links: ARGHasLinks = None,
    folder_ids: Annotated[
        list[str] | None,
        argdesc("List of parent folder IDs to filter by"),
    ] = None,
    names: Annotated[
        list[str] | None,
        argdesc("Filter by a list of names"),
    ] = None,
    names_ci: Annotated[
        list[str] | None,
        argdesc("Filter by a list of names (case insensitive)"),
    ] = None,
    name_ex: Annotated[
        str | None,
        argdesc("Match product names by a regular expression"),
    ] = None,
    path_ex: Annotated[
        str | None,
        argdesc("Match product by a regex of the parent folder path regex"),
    ] = None,
    product_types: Annotated[
        list[str] | None,
        argdesc("List of product types to filter by"),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        argdesc("List of statuses to filter by"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        argdesc("List of tags to filter by"),
    ] = None,
    search: Annotated[
        str | None,
        argdesc("Fuzzy text search filter"),
    ] = None,
    filter: Annotated[
        str | None,
        argdesc("Filter products using QueryFilter"),
    ] = None,
    version_filter: Annotated[
        str | None,
        argdesc("Filter products by their versions using QueryFilter"),
    ] = None,
    sort_by: Annotated[
        str | None,
        sortdesc(SORT_OPTIONS),
    ] = None,
) -> ProductsConnection:
    """Return a list of products."""

    project_name = root.project_name
    user = info.context["user"]
    fields = FieldInfo(info, ["products.edges.node", "product"])

    if user.is_guest:
        if not ids:
            return ProductsConnection(edges=[])

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
        "hierarchy.path AS _folder_path",
    ]

    sql_joins = [
        f"""
        INNER JOIN project_{project_name}.folders
        ON folders.id = products.folder_id
        """,
        f"""
        INNER JOIN project_{project_name}.hierarchy AS hierarchy
        ON folders.id = hierarchy.id
        """,
    ]

    sql_cte = []
    sql_conditions = []

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
        validate_type_name_list(product_types)
        sql_conditions.append(
            f"products.product_type IN {SQLTool.array(product_types)}"
        )

    if statuses is not None:
        if not statuses:
            return ProductsConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"products.status IN {SQLTool.array(statuses)}")
    if tags is not None:
        if not tags:
            return ProductsConnection()
        validate_name_list(tags)
        sql_conditions.append(f"products.tags @> {SQLTool.array(tags, curly=True)}")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "products.id", has_links)
        )

    if name_ex is not None:
        sql_conditions.append(f"products.name ~ '{name_ex}'")

    if path_ex is not None:
        # TODO: sanitize
        sql_conditions.append(f"'/' || hierarchy.path ~ '{path_ex}'")

    #
    # Access control
    #

    access_list = None
    if root.__class__.__name__ == "ProjectNode":
        # Selecting products directly from the project node,
        # so we need to check access rights
        user = info.context["user"]
        if user.is_guest:
            # Guests need to provide explicit IDs
            # that is handled above and provides a sufficient
            # level of security.

            # We may use additional checks for version lists in the future
            pass
        else:
            access_list = await folder_access_list(user, project_name)
            if access_list is not None:
                sql_conditions.append(
                    f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
                )

    #
    # Do we need parent folder attributes?
    # And most importantly - do we need to know which are inherited?
    #

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

    if ff_field := fields.find_field("featuredVersion"):
        req_order = ff_field.arguments.get("order") or [
            "hero",
            "latestApproved",
            "latest",
        ]

        if "hero" in req_order:
            sql_cte.append(
                f"""
                hero_versions AS (
                    SELECT DISTINCT ON (product_id) *
                    FROM project_{project_name}.versions
                    WHERE version < 0
                    ORDER BY product_id, created_at DESC
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN hero_versions AS ff_hero
                ON products.id = ff_hero.product_id
                """
            )
            sql_columns.append("to_jsonb(ff_hero.*) as _hero_version_data")

        if "latestApproved" in req_order:
            sql_cte.append(
                f"""
                approved_statuses AS (
                    SELECT name from project_{project_name}.statuses
                    WHERE data->>'state' = 'done'
                )
                """
            )

            sql_cte.append(
                f"""
                latest_approved_versions AS (
                    SELECT DISTINCT ON (v.product_id) v.*
                    FROM project_{project_name}.versions v
                    JOIN approved_statuses AS s
                    ON v.status = s.name
                    ORDER BY v.product_id, v.version DESC
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN latest_approved_versions AS ff_latest_approved
                ON products.id = ff_latest_approved.product_id
                """
            )
            sql_columns.append(
                "to_jsonb(ff_latest_approved.*) as _latest_approved_version_data"
            )

        if "latest" in req_order:
            sql_cte.append(
                f"""
                latest_versions AS (
                    SELECT DISTINCT ON (product_id) *
                    FROM project_{project_name}.versions
                    WHERE version >= 0
                    ORDER BY product_id, version DESC
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN latest_versions AS ff_latest
                ON products.id = ff_latest.product_id
                """
            )
            sql_columns.append("to_jsonb(ff_latest.*) as _latest_version_data")

    #
    # Version_list
    # (this is probably not needed anymore. Should we remove it?)
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
    # Fuzzy search
    #

    if search:
        terms = slugify(search, make_set=True)
        for term in terms:
            sub_conditions = []
            term = term.replace("'", "''")
            sub_conditions.append(f"products.name ILIKE '%{term}%'")
            sub_conditions.append(f"products.product_type ILIKE '%{term}%'")
            sub_conditions.append(f"hierarchy.path ILIKE '%{term}%'")

            condition = " OR ".join(sub_conditions)
            sql_conditions.append(f"({condition})")

    #
    # Filter (actual product filter)
    #

    if filter:
        column_whitelist = [
            "id",
            "name",
            "folder_id",
            "product_type",
            "attrib",
            "data",
            "active",
            "status",
            "tags",
            "created_at",
            "updated_at",
        ]
        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="products",
        ):
            sql_conditions.append(fcond)

    #
    # Filtering products by versions
    #

    if version_filter:
        column_whitelist = [
            "id",
            "product_id",
            "version",
            "attrib",
            "data",
            "status",
            "tags",
            "created_at",
            "updated_at",
        ]

        fdata = json.loads(version_filter)
        fq = QueryFilter(**fdata)
        fcond = build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="versions",
        )
        if fcond:
            sql_cte.append(
                f"""
                filtered_versions AS (
                    SELECT DISTINCT product_id
                    FROM project_{project_name}.versions
                    WHERE {fcond}
                )
                """
            )

            sql_joins.append(
                """
                INNER JOIN filtered_versions
                ON products.id = filtered_versions.product_id
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

    ordering, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
    )
    sql_conditions.append(paging_conds)

    #
    # Query
    #

    if sql_cte:
        cte = ", ".join(sql_cte)
        cte = f"WITH {cte}"
    else:
        cte = ""

    sql_columns.insert(0, cursor)
    sql_columns_str = ",\n".join(sql_columns)

    query = f"""
        {cte}
        SELECT {sql_columns_str}
        FROM project_{project_name}.products
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    return await resolve(
        ProductsConnection,
        ProductEdge,
        ProductNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_product(root, info: Info, id: str) -> ProductNode:
    """Return a representation node based on its ID"""
    if not id:
        raise BadRequestException("Product ID is not specified")
    connection = await get_products(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Product not found")
    return connection.edges[0].node
