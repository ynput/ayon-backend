import json
from typing import Annotated

from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import VersionsConnection
from ayon_server.graphql.edges import VersionEdge
from ayon_server.graphql.nodes.version import VersionNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    FieldInfo,
    argdesc,
    create_folder_access_list,
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
    validate_user_name_list,
)
from ayon_server.utils import SQLTool, slugify

from .sorting import get_attrib_sort_case, get_status_sort_case

SORT_OPTIONS = {
    "author": "versions.author",
    "version": "versions.version",
    "createdAt": "versions.created_at",
    "updatedAt": "versions.updated_at",
    "createdBy": "versions.created_by",
    "updatedBy": "versions.updated_by",
    "tags": "array_to_string(versions.tags, '')",
    "path": "hierarchy.path || '/' || products.name || '/' || LPAD(versions.version::text, 5, '0')",  # noqa 501
    "productType": "products.product_type",
    "productName": "products.name",
    "folderName": "folders.name",
}


async def get_versions(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    version: int | None = None,
    versions: list[int] | None = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[
        list[str] | None,
        argdesc("List of tags to filter by"),
    ] = None,
    product_ids: Annotated[
        list[str] | None,
        argdesc("List of parent products IDs"),
    ] = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    folder_ids: Annotated[
        list[str] | None,
        argdesc("List of folder IDs to filter by"),
    ] = None,
    include_folder_children: Annotated[
        bool,
        argdesc("Include versions in child folders when folderIds is used"),
    ] = False,
    authors: Annotated[
        list[str] | None,
        argdesc("List of version author user names to filter by."),
    ] = None,
    latest_only: Annotated[
        bool,
        argdesc("DEPRECATED List only latest versions"),
    ] = False,
    hero_only: Annotated[
        bool,
        argdesc("DEPRECATED List only hero versions"),
    ] = False,
    hero_or_latest_only: Annotated[
        bool,
        argdesc("DEPRECATED List hero versions. If hero does not exist, list latest"),
    ] = False,
    has_reviewables: Annotated[
        bool | None,
        argdesc("Filter versions that have reviewables"),
    ] = None,
    featured_only: Annotated[
        list[str] | None,
        argdesc(
            "List only one version for each product, based on the order of flags, "
            "that can be 'hero', 'latestDone' and 'latest."
            "This is a replacement for the deprecated "
            "heroOnly, latestOnly and heroOrLatestOnly"
        ),
    ] = None,
    has_links: ARGHasLinks = None,
    search: Annotated[
        str | None,
        argdesc("Fuzzy text search filter"),
    ] = None,
    filter: Annotated[
        str | None,
        argdesc("Filter tasks using QueryFilter"),
    ] = None,
    task_filter: Annotated[
        str | None,
        argdesc("Filter products by their tasks (via versions) using QueryFilter"),
    ] = None,
    product_filter: Annotated[
        str | None,
        argdesc("Filter versions by their product using QueryFilter"),
    ] = None,
    sort_by: Annotated[
        str | None,
        sortdesc(SORT_OPTIONS),
    ] = None,
) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    user = info.context["user"]
    fields = FieldInfo(info, ["versions.edges.node", "version"])

    #
    # SQL
    #

    sql_cte = []
    sql_conditions = []
    sql_joins = [
        f"""
        INNER JOIN project_{project_name}.products AS products
        ON products.id = versions.product_id
        """,
        f"""
        INNER JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = products.folder_id
        """,
        f"""
        INNER JOIN project_{project_name}.folders AS folders
        ON folders.id = products.folder_id
        """,
        f"""
        LEFT JOIN project_{project_name}.tasks AS tasks
        ON tasks.id = versions.task_id
        """,
    ]

    sql_columns = [
        "versions.*",
        "versions.creation_order AS creation_order",
        "hierarchy.path AS _folder_path",
        "products.name AS _product_name",
    ]

    if fields.any_endswith("hasReviewables") or (has_reviewables is not None):
        sql_cte.append(
            f"""
            reviewables AS (
                SELECT entity_id FROM project_{project_name}.activity_feed
                WHERE entity_type = 'version'
                AND activity_type = 'reviewable'
            )
            """
        )

        sql_columns.append(
            """
            EXISTS (
            SELECT 1 FROM reviewables WHERE entity_id = versions.id
            ) AS has_reviewables
            """
        )

        if has_reviewables is not None:
            if has_reviewables:
                sql_conditions.append(
                    "EXISTS (SELECT 1 FROM reviewables WHERE entity_id = versions.id)"
                )
            else:
                sql_conditions.append(
                    "NOT EXISTS (SELECT 1 FROM reviewables WHERE entity_id = versions.id)"  # noqa 501
                )

    #
    # Direct, version-specific filtering
    #

    # Empty overrides. Skip querying
    if ids == ["0" * 32]:
        return VersionsConnection(edges=[])

    if ids is not None:
        if not ids:
            return VersionsConnection()
        sql_conditions.append(f"versions.id IN {SQLTool.id_array(ids)}")

    if version:
        sql_conditions.append(f"versions.version = {version}")

    if versions is not None:
        if not versions:
            return VersionsConnection()
        sql_conditions.append(f"versions.version IN {SQLTool.array(versions)}")

    if authors is not None:
        if not authors:
            return VersionsConnection()
        validate_user_name_list(authors)
        sql_conditions.append(f"versions.author IN {SQLTool.array(authors)}")

    if statuses is not None:
        if not statuses:
            return VersionsConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"versions.status IN {SQLTool.array(statuses)}")

    if tags is not None:
        if not tags:
            return VersionsConnection()
        validate_name_list(tags)
        sql_conditions.append(f"versions.tags @> {SQLTool.array(tags, curly=True)}")

    if product_ids is not None:
        if not product_ids:
            return VersionsConnection()
        sql_conditions.append(f"versions.product_id IN {SQLTool.id_array(product_ids)}")
    elif root.__class__.__name__ == "ProductNode":
        sql_conditions.append(f"versions.product_id = '{root.id}'")

    if task_ids:
        sql_conditions.append(f"versions.task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"versions.task_id = '{root.id}'")

    if folder_ids is not None:
        if not folder_ids:
            return VersionsConnection()

        if include_folder_children:
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

        else:
            sql_conditions.append(
                f"products.folder_id IN {SQLTool.id_array(folder_ids)}"
            )

    #
    # Always-on CTEs (to get latest and hero versions)
    #

    sql_cte.extend(
        [
            f"""
            latest_versions AS (
                SELECT DISTINCT ON (product_id) id, version, product_id
                FROM project_{project_name}.versions
                WHERE version >= 0
                ORDER BY product_id, version DESC
            )
            """,
            f"""
            done_statuses AS (
                SELECT name from project_{project_name}.statuses
                WHERE data->>'state' = 'done'
            )
            """,
            f"""
            latest_done_versions AS (
                SELECT DISTINCT ON (v.product_id) v.id, v.version, v.product_id
                FROM project_{project_name}.versions v
                JOIN done_statuses ds
                ON v.status = ds.name
                WHERE v.version >= 0
                ORDER BY v.product_id, v.version DESC
            )
            """,
            f"""
            hero_versions AS (
                SELECT version.id id, hero_version.id AS hero_version_id
                FROM project_{project_name}.versions AS version
                JOIN project_{project_name}.versions AS hero_version
                ON hero_version.product_id = version.product_id
                AND hero_version.version < 0
                AND ABS(hero_version.version) = version.version
            )
            """,
        ]
    )

    # Map versions to their hero versions

    sql_joins.append(
        """
        LEFT JOIN hero_versions
        ON hero_versions.id = versions.id
        """
    )
    sql_columns.append("hero_versions.hero_version_id AS hero_version_id")

    sql_joins.append(
        """
        LEFT JOIN latest_versions AS lv
        ON lv.id = versions.id
        """
    )
    sql_columns.append("lv IS NOT NULL AS is_latest")

    sql_joins.append(
        """
        LEFT JOIN latest_done_versions AS ldv
        ON ldv.id = versions.id
        """
    )
    sql_columns.append("ldv IS NOT NULL AS is_latest_done")

    #
    # Filtering by latest / hero versions
    # (deprecated part)
    #

    if latest_only:
        sql_conditions.append("lv.id IS NOT NULL")

    elif hero_only:
        # This returns actual (negative) hero versions only
        # Not versions that point to hero via hero_versions CTE
        sql_conditions.append("versions.version < 0")

    elif hero_or_latest_only:
        # Same as above, but include latest if no hero exists
        # This is provided mainly for backward compatibility and the pipeline
        # The frontend uses new featuredVersion filter instead

        sql_conditions.append("(versions.version < 0 OR lv IS NOT NULL)")

    #
    # Filtering by featured versions
    #

    if featured_only is not None:
        if not featured_only:
            return VersionsConnection()

        # for every product, select only one version based on the order
        # of flags in featured_only.

        where_clauses = []
        order_clause = "CASE "
        for idx, flag in enumerate(featured_only):
            if flag not in ("hero", "latestDone", "latest"):
                raise BadRequestException(
                    "Invalid featuredOnly value: "
                    f"'{flag}'. Must be one of 'hero', 'latestDone', 'latest'."
                )
            if flag == "hero":
                where_clauses.append("hv.id IS NOT NULL")
                order_clause += f"WHEN hv.id IS NOT NULL THEN {idx} "
            elif flag == "latestDone":
                where_clauses.append("ldv.id IS NOT NULL")
                order_clause += f"WHEN ldv.id IS NOT NULL THEN {idx} "
            elif flag == "latest":
                where_clauses.append("lv.id IS NOT NULL")
                order_clause += f"WHEN lv.id IS NOT NULL THEN {idx} "

        order_clause += f"ELSE {len(featured_only)} END"

        sql_cte.append(
            f"""
            featured_versions AS (
                SELECT DISTINCT ON (versions.product_id) versions.id
                FROM project_{project_name}.versions AS versions
                LEFT JOIN latest_versions AS lv
                ON lv.id = versions.id
                LEFT JOIN latest_done_versions AS ldv
                ON ldv.id = versions.id
                LEFT JOIN hero_versions AS hv
                ON hv.id = versions.id
                WHERE {' OR '.join(where_clauses)}
                ORDER BY versions.product_id, {order_clause}
            )
            """
        )

        sql_joins.append(
            """
            INNER JOIN featured_versions AS fv
            ON fv.id = versions.id
            """
        )

    #
    # Filtering by links
    #

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "versions.id", has_links)
        )

    #
    # Access control
    #

    if user.is_guest:
        sql_cte.append(
            f"""guest_accessible_versions AS (
                SELECT DISTINCT(entity_id)
                FROM project_{project_name}.entity_list_items i
                JOIN project_{project_name}.entity_lists l
                ON l.id = i.entity_list_id
                AND l.entity_type = 'version'
                AND (
                        (l.access->'__guests__')::integer > 0
                        OR (l.access->'guest:{user.attrib.email}')::integer > 0
                    )
                )
            """
        )
        sql_joins.append(
            """
            INNER JOIN guest_accessible_versions AS gav
            ON gav.entity_id = versions.id
            """
        )

    elif not user.is_manager:
        access_list = await create_folder_access_list(root, info)
        if access_list is not None:
            sql_conditions.append(
                f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
            )

    #
    # Fuzzy search
    #

    if search:
        terms = slugify(search, make_set=True, min_length=2)

        for term in terms:
            sub_conditions = []
            if term.isdigit():
                sub_conditions.append(f"versions.version = {int(term)}")
            elif term.startswith("v") and term[1:].isdigit():
                sub_conditions.append(f"versions.version = {int(term[1:])}")

            sub_conditions.append(f"products.name ILIKE '%{term}%'")
            sub_conditions.append(f"products.product_type ILIKE '%{term}%'")
            sub_conditions.append(f"hierarchy.path ILIKE '%{term}%'")

            condition = " OR ".join(sub_conditions)
            sql_conditions.append(f"({condition})")

    #
    # Filter
    #

    if filter:
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
            "created_by",
            "updated_by",
            # virtual
            "product_type",
            "task_type",
            "folder_type",
        ]

        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="versions",
            column_map={
                "product_type": "products.product_type",
                "task_type": "tasks.task_type",
                "folder_type": "folders.folder_type",
            },
        ):
            sql_conditions.append(fcond)

    if product_filter:
        column_whitelist = [
            "id",
            "name",
            "folder_id",
            "product_type",
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

        fdata = json.loads(product_filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="products",
        ):
            sql_conditions.append(fcond)

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
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="tasks",
        ):
            sql_conditions.append(fcond)

    #
    # Pagination
    #

    order_by = ["versions.creation_order"]
    if sort_by is not None:
        if sort_by == "status":
            status_type_case = get_status_sort_case(project, "versions.status")
            order_by.insert(0, status_type_case)
        elif sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            attr_case = await get_attrib_sort_case(attr_name, "versions.attrib")
            order_by.insert(0, attr_case)
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

    query = f"""
        {cte}
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.versions AS versions
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    # print()
    # print("Versions query:")
    # print(query)
    # print()

    return await resolve(
        VersionsConnection,
        VersionEdge,
        VersionNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_version(root, info: Info, id: str) -> VersionNode:
    """Return a task node based on its ID"""
    if not id:
        raise BadRequestException("Version ID not specified")
    connection = await get_versions(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Version not found")
    return connection.edges[0].node
