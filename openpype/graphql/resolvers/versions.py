from typing import Annotated
from strawberry.types import Info

from openpype.utils import SQLTool, EntityID
from openpype.lib.postgres import Postgres

from ..nodes.version import VersionNode
from ..connections import VersionsConnection
from ..edges import VersionEdge

from .common import argdesc, resolve
from .common import ARGFirst, ARGAfter, ARGLast, ARGBefore, ARGIds


async def get_versions(
    root,
    info: Info,

    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,

    subset_ids: Annotated[
        list[str] | None,
        argdesc("List of parent subsets IDs")
    ] = None,

    authors: Annotated[
        list[str] | None,
        argdesc("List of version author user names to filter by.")
    ] = None,

    version: int = None,

) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name

    #
    # Conditions
    #

    conditions = []
    if ids:
        conditions.append(f"id IN {SQLTool.id_array(ids)}")
    if version:
        conditions.append(f"version = {version}")
    if authors:
        conditions.append(f"author IN {SQLTool.id_array(authors)}")
    if subset_ids:
        conditions.append(f"subset_id IN {SQLTool.id_array(subset_ids)}")
    elif root.__class__.__name__ == "SubsetNode":
        conditions.append(f"subset_id = '{root.id}'")

    #
    # Pagination
    #

    pagination = ""
    if first:
        pagination += f"ORDER BY id ASC LIMIT {first}"
        if after:
            conditions.append(f"id > '{EntityID.parse(after)}'")
    elif last:
        pagination += f"ORDER BY id DESC LIMIT {first}"
        if before:
            conditions.append(f"id < '{EntityID.parse(before)}'")

    #
    # Query
    #

    query = f"""
        SELECT *
        FROM project_{project_name}.versions
        {SQLTool.conditions(conditions)}
    """

    return await resolve(
        VersionsConnection,
        VersionEdge,
        VersionNode,
        project_name,
        query,
        first,
        last
    )


async def get_latest_version(root):
    """Return the latest version of the subset.

    This is not used since it is replaced with latest_version_loader
    """

    async for record in Postgres.iterate(
        f"""
        SELECT *
        FROM project_{root.project_name}.versions
        WHERE subset_id = '{root.id}'
        ORDER BY version DESC
        """
    ):
        return VersionNode.from_record(root.project_name, record)
    return None


async def get_version(root, info: Info, id: str) -> VersionNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_versions(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
