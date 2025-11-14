import json
from typing import Annotated

from ayon_server.access.utils import folder_access_list
from ayon_server.entities import ProjectEntity
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

from .sorting import get_attrib_sort_case, get_status_sort_case

SORT_OPTIONS = {
    "name": "products.name",
    "path": "hierarchy.path || '/' || products.name",
    "productType": "products.product_type",
    "productBaseType": "products.product_base_type",
    "folderName": "folders.name",
    "status": "products.status",
    "createdAt": "products.created_at",
    "updatedAt": "products.updated_at",
    "createdBy": "products.created_by",
    "updatedBy": "products.updated_by",
    "tags": "array_to_string(products.tags, '')",
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
    include_folder_children: Annotated[
        bool,
        argdesc("Include versions in child folders when folderIds is used"),
    ] = False,
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
    product_base_types: Annotated[
        list[str] | None, argdesc("List of base types")
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
    task_filter: Annotated[
        str | None,
        argdesc("Filter products by their tasks (via versions) using QueryFilter"),
    ] = None,
    sort_by: Annotated[
        str | None,
        sortdesc(SORT_OPTIONS),
    ] = None,
) -> ProductsConnection:
    """Return a list of products."""

    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    user = info.context["user"]
    fields = FieldInfo(info, ["products.edges.node", "product"])

    if user.is_guest:
        if not ids:
            return ProductsConnection(edges=[])

    #
    # SQL
    #

    sql_columns = [
        "products.*",
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
        if not include_folder_children:
            sql_conditions.append(
                f"products.folder_id IN {SQLTool.id_array(folder_ids)}"
            )
        else:
            sql_cte.append(
                f"""
                top_folder_paths AS (
                    SELECT path FROM project_{project_name}.hierarchy
                    WHERE id IN {SQLTool.id_array(folder_ids)}
                )
                """
            )
            sql_cte.append(
                f"""
                child_folder_ids AS (
                    SELECT id FROM project_{project_name}.hierarchy
                    WHERE EXISTS (
                        SELECT 1 FROM top_folder_paths
                        WHERE project_{project_name}.hierarchy.path
                        LIKE top_folder_paths.path || '/%'
                    )
                    OR project_{project_name}.hierarchy.path = ANY(
                        SELECT path FROM top_folder_paths
                    )
                )
                """
            )
            sql_joins.append(
                """
                INNER JOIN child_folder_ids AS cfi
                ON cfi.id = products.folder_id
                """
            )

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

    if product_base_types is not None:
        if not product_base_types:
            return ProductsConnection()
        validate_name_list(product_base_types)
        sql_conditions.append(
            f"products.product_base_type IN {SQLTool.array(product_base_types)}"
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
            "latestDone",
            "latest",
        ]

        sql_cte.append(
            f"""
            reviewables AS (
                SELECT entity_id FROM project_{project_name}.activity_feed
                WHERE entity_type = 'version'
                AND activity_type = 'reviewable'
            )
            """
        )

        if "hero" in req_order:
            sql_cte.append(
                f"""
                hero_versions AS (
                    SELECT
                        distinct on (versions.product_id)
                        versions.*,
                        hero_versions.id AS hero_version_id,
                        rv.entity_id IS NOT NULL AS has_reviewables
                    FROM project_{project_name}.versions AS versions

                    JOIN project_{project_name}.versions AS hero_versions
                    ON hero_versions.product_id = versions.product_id
                    AND hero_versions.version < 0
                    AND ABS(hero_versions.version) = versions.version

                    LEFT JOIN reviewables AS rv
                    ON versions.id = rv.entity_id

                    ORDER BY versions.product_id, versions.version DESC
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN hero_versions AS ff_hero
                ON ff_hero.product_id = products.id
                """
            )
            sql_columns.append("to_jsonb(ff_hero.*) as _hero_version_data")

        if "latestDone" in req_order:
            sql_cte.append(
                f"""
                done_statuses AS (
                    SELECT name from project_{project_name}.statuses
                    WHERE data->>'state' = 'done'
                )
                """
            )

            sql_cte.append(
                f"""
                latest_done_versions AS (
                    SELECT
                        DISTINCT ON (versions.product_id)
                        versions.*,
                        rv.entity_id IS NOT NULL AS has_reviewables
                    FROM project_{project_name}.versions

                    JOIN done_statuses AS s
                    ON versions.status = s.name

                    LEFT JOIN reviewables AS rv
                    ON versions.id = rv.entity_id

                    ORDER BY versions.product_id, versions.version DESC
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN latest_done_versions AS ff_latest_done
                ON products.id = ff_latest_done.product_id
                """
            )
            sql_columns.append(
                "to_jsonb(ff_latest_done.*) as _latest_done_version_data"
            )

        if "latest" in req_order:
            sql_cte.append(
                f"""
                latest_versions AS (
                    SELECT
                        DISTINCT ON (versions.product_id) versions.*,
                        rv.entity_id IS NOT NULL AS has_reviewables
                    FROM project_{project_name}.versions

                    LEFT JOIN reviewables AS rv
                    ON versions.id = rv.entity_id

                    WHERE versions.version >= 0
                    ORDER BY versions.product_id, versions.version DESC
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
            "product_base_type",
            "status",
            "attrib",
            "data",
            "tags",
            "active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
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
    # Filtering products by versions and tasks
    #

    if version_filter or task_filter:
        version_cond = ""
        task_cond = ""

        if version_filter:
            column_whitelist = [
                "id",
                "version",
                "product_id",
                "task_id",
                "author",
                "status",
                "attrib",
                "data",
                "tags",
                "active",
                "created_at",
                "updated_at",
                # virtual
                "product_type",
                "product_base_type",
            ]

            fdata = json.loads(version_filter)
            fq = QueryFilter(**fdata)
            fcond = build_filter(
                fq,
                column_whitelist=column_whitelist,
                table_prefix="versions",
                column_map={
                    "product_type": "products.product_type",
                    "product_base_type": "products.product_base_type",
                },
            )
            if fcond:
                version_cond = f"{fcond}"

        if task_filter:
            column_whitelist = [
                "id",
                "name",
                "label",
                "task_type",
                "assignees",
                "status",
                "attrib",
                "data",
                "tags",
                "active",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
            ]

            fdata = json.loads(task_filter)
            fq = QueryFilter(**fdata)
            fcond = build_filter(
                fq,
                column_whitelist=column_whitelist,
                table_prefix="tasks",
            )
            if fcond:
                task_cond = f"{fcond}"

        if version_cond or task_cond:
            vtconds = []
            tjoin = ""
            if version_cond:
                vtconds.append(version_cond)
            if task_cond:
                vtconds.append(task_cond)
                tjoin = f"""
                LEFT JOIN project_{project_name}.tasks
                ON versions.task_id = tasks.id
                """

            vtcondstr = "WHERE " + " AND ".join(vtconds)

            sql_cte.append(
                f"""
                filtered_versions AS (
                    SELECT DISTINCT product_id
                    FROM project_{project_name}.versions
                    JOIN project_{project_name}.products
                    ON versions.product_id = products.id
                    {tjoin}
                    {vtcondstr}

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
        if sort_by == "status":
            status_type_case = get_status_sort_case(project, "products.status")
            order_by.insert(0, status_type_case)
        elif sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            attr_case = await get_attrib_sort_case(attr_name, "products.attrib")
            order_by.insert(0, attr_case)
        elif sort_by == "version":
            # count by product version count
            sql_cte.append(
                f"""
                product_version_counts AS (
                    SELECT
                        product_id,
                        COUNT(*) AS version_count
                    FROM project_{project_name}.versions
                    WHERE version >= 0
                    GROUP BY product_id
                )
                """
            )
            sql_joins.append(
                """
                LEFT JOIN product_version_counts AS pvc
                ON pvc.product_id = products.id
                """
            )
            order_by.insert(0, "COALESCE(pvc.version_count, 0)")

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

    # print()
    # print (query)
    # print()
    #
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
