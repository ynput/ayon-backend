import json
from typing import Annotated

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

SORT_OPTIONS = {
    "version": "versions.version",
    "status": "versions.status",
    "createdAt": "versions.created_at",
    "updatedAt": "versions.updated_at",
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
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    product_ids: Annotated[
        list[str] | None,
        argdesc("List of parent products IDs"),
    ] = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    authors: Annotated[
        list[str] | None,
        argdesc("List of version author user names to filter by."),
    ] = None,
    latestOnly: Annotated[
        bool,
        argdesc("List only latest versions"),
    ] = False,
    heroOnly: Annotated[
        bool,
        argdesc("List only hero versions"),
    ] = False,
    heroOrLatestOnly: Annotated[
        bool,
        argdesc("List hero versions. If hero does not exist, list latest"),
    ] = False,
    has_links: ARGHasLinks = None,
    search: Annotated[str | None, argdesc("Fuzzy text search filter")] = None,
    filter: Annotated[str | None, argdesc("Filter tasks using QueryFilter")] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name
    user = info.context["user"]
    fields = FieldInfo(info, ["versions.edges.node", "version"])

    #
    # SQL
    #
    sql_cte = []

    sql_columns = [
        "versions.id AS id",
        "versions.version AS version",
        "versions.product_id AS product_id",
        "versions.task_id AS task_id",
        "versions.thumbnail_id AS thumbnail_id",
        "versions.author AS author",
        "versions.attrib AS attrib",
        "versions.data AS data",
        "versions.status AS status",
        "versions.tags AS tags",
        "versions.active AS active",
        "versions.created_at AS created_at",
        "versions.updated_at AS updated_at",
        "versions.creation_order AS creation_order",
    ]

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
            SELECT 1 FROM reviewables WHERE entity_id = versions.id
            ) AS has_reviewables
            """
        )

    sql_conditions = []
    sql_joins = []

    needs_hierarchy = False

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

    if latestOnly:
        sql_conditions.append(
            f"""
            versions.id IN (
            SELECT l.ids[array_upper(l.ids, 1)]
            FROM project_{project_name}.version_list as l
            )
            """
        )
    elif heroOnly:
        sql_conditions.append("versions.version < 0")
    elif heroOrLatestOnly:
        sql_conditions.append(
            f"""
            (versions.version < 0
            OR versions.id IN (
                SELECT l.ids[array_upper(l.ids, 1)]
                FROM project_{project_name}.version_list as l
                WHERE l.versions[1] >= 0
            )
            )
            """
        )

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "versions.id", has_links)
        )

    if user.is_guest:
        if not ids:
            return VersionsConnection(edges=[])
        # Guest users can only access version by their ID.
        # So listing versions is not allowed.
        pass

    else:
        access_list = await create_folder_access_list(root, info)
        if access_list is not None:
            sql_conditions.append(
                f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
            )
            needs_hierarchy = True

    if search:
        needs_hierarchy = True
        terms = slugify(search, make_set=True, min_length=2)

        for term in terms:
            sub_conditions = []
            if term.isdigit():
                sub_conditions.append(f"versions.version = {int(term)}")
            elif term.startswith("v") and term[1:].isdigit():
                sub_conditions.append(f"versions.version = {int(term[1:])}")

            term = term.replace("'", "''")  # Escape single quotes
            sub_conditions.append(f"products.name ILIKE '%{term}%'")
            sub_conditions.append(f"products.product_type ILIKE '%{term}%'")
            sub_conditions.append(f"hierarchy.path ILIKE '%{term}%'")

            condition = " OR ".join(sub_conditions)
            sql_conditions.append(f"({condition})")

    if fields.any_endswith("path") or fields.any_endswith("parents"):
        needs_hierarchy = True

    if needs_hierarchy:
        sql_columns.append("hierarchy.path AS _folder_path")
        sql_columns.append("products.name AS _product_name")

        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.products AS products
            ON products.id = versions.product_id
            """
        )

        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.hierarchy AS hierarchy
            ON hierarchy.id = products.folder_id
            """
        )

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
            table_prefix="versions",
        ):
            sql_conditions.append(fcond)

    #
    # Pagination
    #

    order_by = ["versions.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"versions.attrib->>'{sort_by[7:]}'")
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
