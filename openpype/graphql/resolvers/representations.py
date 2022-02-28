from typing import Annotated

from strawberry.types import Info

from openpype.utils import EntityID, SQLTool

from ..connections import RepresentationsConnection
from ..edges import RepresentationEdge
from ..nodes.representation import RepresentationNode
from .common import ARGAfter, ARGBefore, ARGFirst, ARGIds, ARGLast, argdesc, resolve


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
) -> RepresentationsConnection:
    """Return a list of representations."""

    project_name = root.project_name

    #
    # Conditions
    #

    # TODO: Query data only when needed
    # that means when user wants context or files data

    sql_columns = [
        "representations.id AS id",
        "representations.name AS name",
        "representations.version_id AS version_id",
        "representations.attrib AS attrib",
        "representations.data AS data",
        "representations.active AS active",
        "representations.created_at AS created_at",
        "representations.updated_at AS updated_at",
    ]

    sql_joins = []
    sql_conditions = []

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if version_ids is not None:
        sql_conditions.append(f"version_id IN {SQLTool.id_array(version_ids)}")
    elif root.__class__.__name__ == "VersionNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"version_id = '{root.id}'")

    if name is not None:
        sql_conditions.append(f"name ILIKE '{name}'")

    #
    # Files
    #

    if local_site is not None:
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.files as local_files
                ON local_files.representation_id = id
            """
        )
        sql_columns.append("local_files.data AS local_state")
        sql_conditions.append(f"local_files.site_name = '{local_site}'")

    if remote_site is not None:
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.files as remote_files
                ON remote_files.representation_id = id
            """
        )
        sql_columns.append("remote_files.data AS remote_state")
        sql_conditions.append(f"remote_files.site_name = '{remote_site}'")

    #
    # Pagination
    #

    pagination = ""
    if first:
        pagination += "ORDER BY id ASC"
        if after:
            sql_conditions.append(f"id > '{EntityID.parse(after)}'")
    elif last:
        pagination += "ORDER BY id DESC"
        if before:
            sql_conditions.append(f"id < '{EntityID.parse(before)}'")

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
