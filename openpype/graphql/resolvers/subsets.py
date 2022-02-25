from typing import Annotated
from strawberry.types import Info

from openpype.utils import SQLTool, EntityID

from ..connections import SubsetsConnection
from ..nodes.subset import SubsetNode
from ..edges import SubsetEdge

from .common import FieldInfo, argdesc, resolve
from .common import ARGFirst, ARGAfter, ARGLast, ARGBefore, ARGIds


async def get_subsets(
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
    name: Annotated[str | None, argdesc("Text string to filter name by")] = None,
    families: Annotated[
        list[str] | None, argdesc("List of families to filter by")
    ] = None,
) -> SubsetsConnection:
    """Return a list of subsets."""

    project_name = root.project_name
    fields = FieldInfo(info, ["subsets.edges.node", "subset"])

    #
    # SQL
    #

    sql_columns = [
        "subsets.id AS id",
        "subsets.name AS name",
        "subsets.folder_id AS folder_id",
        "subsets.family AS family",
        "subsets.attrib AS attrib",
        "subsets.data AS data",
        "subsets.active AS active",
        "subsets.created_at AS created_at",
        "subsets.updated_at AS updated_at",
    ]
    sql_conditions = []
    sql_joins = []

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")

    if folder_ids:
        sql_conditions.append(f"folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"folder_id = '{root.id}'")

    if families:
        sql_conditions.append(f"family IN {SQLTool.array(families)}")

    if name:
        sql_conditions.append(f"name ILIKE '{name}'")

    #
    # Join with folders if parent folder is requested
    #

    if "folder" in fields:
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.folder_type AS _folder_folder_type",
                "folders.parent_id AS _folder_parent_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
            ]
        )
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.folders
                ON folders.id = subsets.folder_id
            """
        )

        if any(
            field.endswith("folder.path") or field.endswith("folder.parents")
            for field in fields
        ):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"""
                LEFT JOIN
                    project_{project_name}.hierarchy AS hierarchy
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
                ON subsets.id = version_list.subset_id
            """
        )

    #
    # Pagination
    #

    pagination = ""
    if first:
        pagination += f"ORDER BY subsets.id ASC LIMIT {first}"
        if after:
            sql_conditions.append(f"subsets.id > '{EntityID.parse(after)}'")
    elif last:
        pagination += f"ORDER BY subsets.id DESC LIMIT {first}"
        if before:
            sql_conditions.append(f"subsets.id < '{EntityID.parse(before)}'")

    #
    # Query
    #

    query = f"""
        SELECT {", ".join(sql_columns)}
        FROM project_{project_name}.subsets
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        SubsetsConnection,
        SubsetEdge,
        SubsetNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_subset(root, info: Info, id: str) -> SubsetNode | None:
    """Return a representation node based on its ID"""
    if not id:
        return None
    connection = await get_subsets(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
