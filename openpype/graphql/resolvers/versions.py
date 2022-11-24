from typing import Annotated

from strawberry.types import Info

from openpype.graphql.connections import VersionsConnection
from openpype.graphql.edges import VersionEdge
from openpype.graphql.nodes.version import VersionNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
)
from openpype.utils import SQLTool


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
    subset_ids: Annotated[
        list[str] | None,
        argdesc("List of parent subsets IDs"),
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
) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name

    #
    # SQL
    #

    sql_columns = [
        "versions.id AS id",
        "versions.version AS version",
        "versions.subset_id AS subset_id",
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

    # sql_joins = []
    sql_conditions = []
    sql_joins = []

    # Empty overrides. Skip querying
    if ids == ["0" * 32]:
        return VersionsConnection(edges=[])

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")
    if version:
        sql_conditions.append(f"version = {version}")
    if versions:
        sql_conditions.append(f"version IN {SQLTool.array(versions)}")
    if authors:
        sql_conditions.append(f"author IN {SQLTool.id_array(authors)}")

    if subset_ids:
        sql_conditions.append(f"subset_id IN {SQLTool.id_array(subset_ids)}")
    elif root.__class__.__name__ == "SubsetNode":
        sql_conditions.append(f"subset_id = '{root.id}'")
    if task_ids:
        sql_conditions.append(f"task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"task_id = '{root.id}'")

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

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.subsets AS subsets
                ON subsets.id = versions.subset_id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON hierarchy.id = subsets.folder_id
                """,
            ]
        )

    #
    # Pagination
    #

    order_by = "versions.creation_order"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {", ".join(sql_columns)}
        FROM project_{project_name}.versions AS versions
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        VersionsConnection,
        VersionEdge,
        VersionNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
        order_by=order_by,
    )


async def get_version(root, info: Info, id: str) -> VersionNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_versions(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
