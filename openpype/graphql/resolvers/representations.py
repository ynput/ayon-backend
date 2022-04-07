from typing import Annotated

from strawberry.types import Info

from openpype.utils import SQLTool

from ..connections import RepresentationsConnection
from ..edges import RepresentationEdge
from ..nodes.representation import RepresentationNode
from .common import (
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


async def get_representations(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    local_site: str | None = None,
    remote_site: str | None = None,
    version_ids: Annotated[
        list[str] | None, argdesc("List of parent version IDs to filter by")
    ] = None,
    name: Annotated[str | None, argdesc("Text string to filter name by")] = None,
    has_links: ARGHasLinks = None,
) -> RepresentationsConnection:
    """Return a list of representations."""

    project_name = root.project_name

    #
    # Conditions
    #

    sql_columns = [
        "representations.id AS id",
        "representations.name AS name",
        "representations.version_id AS version_id",
        "representations.attrib AS attrib",
        "representations.active AS active",
        "representations.created_at AS created_at",
        "representations.updated_at AS updated_at",
    ]

    sql_joins = []
    sql_conditions = []

    if local_site or remote_site:
        sql_columns.append("representations.data AS data")

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if version_ids is not None:
        sql_conditions.append(f"version_id IN {SQLTool.id_array(version_ids)}")
    elif root.__class__.__name__ == "VersionNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"version_id = '{root.id}'")

    if name is not None:
        sql_conditions.append(f"name ILIKE '{name}'")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "representations.id", has_links)
        )

    #
    # ACL
    #

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.versions AS versions
                ON versions.id = representations.version_id
                """,
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
    # Files
    #

    if local_site is not None:
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.files as local_files
            ON local_files.representation_id = id
            AND local_files.site_name = '{local_site}'
            """
        )
        sql_columns.append("local_files.data AS local_data")
        sql_columns.append("local_files.status AS local_status")

    if remote_site is not None:
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.files as remote_files
            ON remote_files.representation_id = id
            AND remote_files.site_name = '{remote_site}'
            """
        )
        sql_columns.append("remote_files.data AS remote_data")
        sql_columns.append("remote_files.status AS remote_status")

    #
    # Pagination
    #

    pagination = ""
    order_by = "id"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {', '.join(sql_columns)}
        FROM project_{project_name}.representations
        {' '.join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        RepresentationsConnection,
        RepresentationEdge,
        RepresentationNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_representation(
    root,
    info: Info,
    id: str,
    local_site: str | None = None,
    remote_site: str | None = None,
) -> RepresentationNode | None:
    """Return a representation node based on its ID"""
    if not id:
        return None
    connection = await get_representations(
        root, info, ids=[id], local_site=local_site, remote_site=remote_site
    )
    if not connection.edges:
        return None
    return connection.edges[0].node
