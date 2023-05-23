from typing import Annotated

from strawberry.types import Info

from ayon_server.access.utils import folder_access_list
from ayon_server.graphql.connections import SubsetsConnection
from ayon_server.graphql.edges import SubsetEdge
from ayon_server.graphql.nodes.subset import SubsetNode
from ayon_server.graphql.resolvers.common import (
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
    sortdesc,
)
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool

SORT_OPTIONS = {
    "name": "subsets.name",
    "family": "subsets.family",
    "createdAt": "subsets.created_at",
    "updatedAt": "subsets.updated_at",
}


empty_connection = SubsetsConnection(
    edges=[],
    page_info=create_pagination(["subsets.creation_order"], 0, 0, 0, 0),
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
    names: Annotated[list[str] | None, argdesc("Filter by a list of names")] = None,
    families: Annotated[
        list[str] | None, argdesc("List of families to filter by")
    ] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
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
        "subsets.status AS status",
        "subsets.tags AS tags",
        "subsets.active AS active",
        "subsets.created_at AS created_at",
        "subsets.updated_at AS updated_at",
        "subsets.creation_order AS creation_order",
    ]
    sql_conditions = []
    sql_joins = []

    if ids is not None:
        if not ids:
            return empty_connection
        sql_conditions.append(f"subsets.id IN {SQLTool.id_array(ids)}")

    if folder_ids is not None:
        if not folder_ids:
            return empty_connection
        sql_conditions.append(f"subsets.folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"subsets.folder_id = '{root.id}'")

    if names is not None:
        if not names:
            return empty_connection
        validate_name_list(names)
        sql_conditions.append(f"subsets.name IN {SQLTool.array(names)}")

    if families is not None:
        if not families:
            return empty_connection
        validate_name_list(families)
        sql_conditions.append(f"subsets.family IN {SQLTool.array(families)}")

    if statuses is not None:
        if not statuses:
            return empty_connection
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")
    if tags is not None:
        if not tags:
            return empty_connection
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "subsets.id", has_links)
        )

    access_list = None
    if root.__class__.__name__ == "ProjectNode":
        # Selecting subsets directly from the project node,
        # so we need to check access rights
        user = info.context["user"]
        access_list = await folder_access_list(user, project_name)
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
            ]
        )
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = subsets.folder_id
            """
        )

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

    order_by = ["subsets.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"subsets.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    paging_fields = FieldInfo(info, ["subsets"])
    need_cursor = paging_fields.has_any(
        "subsets.pageInfo.startCursor",
        "subsets.pageInfo.endCursor",
        "subsets.edges.cursor",
    )

    pagination, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
        need_cursor=need_cursor,
    )
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
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
