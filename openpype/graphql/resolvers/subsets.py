from typing import Annotated
from strawberry.types import Info

from openpype.access.utils import folder_access_list
from openpype.utils import SQLTool
from openpype.graphql.connections import SubsetsConnection
from openpype.graphql.edges import SubsetEdge
from openpype.graphql.nodes.subset import SubsetNode
from openpype.graphql.resolvers.common import (
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
)


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
    has_links: ARGHasLinks = None,
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

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "subsets.id", has_links)
        )

    access_list = None
    if root.__class__.__name__ == "ProjectNode":
        # Selecting subsets directly from the project node,
        # so we need to check access rights
        user = info.context["user"]
        access_list = await folder_access_list(user, project_name, "read")
        if access_list is not None:
            sql_conditions.append(
                f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
            )

    #
    # Join with folders if parent folder is requested
    #

    if "folder" in fields or (access_list is not None):
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.folder_type AS _folder_folder_type",
                "folders.parent_id AS _folder_parent_id",
                "folders.thumbnail_id AS _folder_thumbnail_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
            ]
        )
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = subsets.folder_id
            """
        )

        if any(
            field.endswith("folder.path") or field.endswith("folder.parents")
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
                ON subsets.id = version_list.subset_id
            """
        )

    #
    # Pagination
    #

    order_by = "id"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

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
        order_by=order_by,
    )


async def get_subset(root, info: Info, id: str) -> SubsetNode | None:
    """Return a representation node based on its ID"""
    if not id:
        return None
    connection = await get_subsets(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
