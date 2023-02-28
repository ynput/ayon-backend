from typing import Annotated

from strawberry.types import Info

from ayon_server.entities.core import attribute_library
from ayon_server.graphql.connections import FoldersConnection
from ayon_server.graphql.edges import FolderEdge
from ayon_server.graphql.nodes.folder import FolderNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    AtrributeFilterInput,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.types import validate_name, validate_name_list, validate_status_list
from ayon_server.utils import EntityID, SQLTool

SORT_OPTIONS = {
    "name": "folders.name",
    "status": "folders.status",
    "createdAt": "folders.created_at",
    "updatedAt": "folders.updated_at",
    "folderType": "folders.folder_type",
}


async def get_folders(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    parent_id: Annotated[
        str | None,
        argdesc(
            """
            ID of the parent folder.
            Use 'root' to get top level folders.
            """
        ),
    ] = None,
    parent_ids: Annotated[list[str] | None, argdesc("List of parent ids.")] = None,
    attributes: Annotated[
        list[AtrributeFilterInput] | None, argdesc("Filter by a list of attributes")
    ] = None,
    folder_types: Annotated[
        list[str] | None, argdesc("List of folder types to filter by")
    ] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    paths: Annotated[list[str] | None, argdesc("List of paths to filter by")] = None,
    path_ex: Annotated[str | None, argdesc("Match paths by regular expression")] = None,
    name: Annotated[
        str | None, argdesc("Text string to filter names by. Use `%` as wildcard.")
    ] = None,
    names: Annotated[
        list[str] | None,
        argdesc("List of names to filter. Only exact matches are returned"),
    ] = None,
    has_children: Annotated[
        bool | None, argdesc("Whether to filter by folders with children")
    ] = None,
    has_subsets: Annotated[
        bool | None, argdesc("Whether to filter by folders with subsets")
    ] = None,
    has_tasks: Annotated[
        bool | None, argdesc("Whether to filter by folders with tasks")
    ] = None,
    has_links: ARGHasLinks = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> FoldersConnection:
    """Return a list of folders."""

    project_name = root.project_name
    fields = FieldInfo(info, ["folders.edges.node", "folder"])

    #
    # SQL
    #

    sql_columns = [
        "folders.id AS id",
        "folders.name AS name",
        "folders.label AS label",
        "folders.active AS active",
        "folders.folder_type AS folder_type",
        "folders.status AS status",
        "folders.tags AS tags",
        "folders.parent_id AS parent_id",
        "folders.thumbnail_id AS thumbnail_id",
        "folders.attrib AS attrib",
        "folders.created_at AS created_at",
        "folders.updated_at AS updated_at",
        "folders.creation_order AS creation_order",
        "pr.attrib AS project_attributes",
        "ex.attrib AS inherited_attributes",
    ]

    sql_joins = [
        f"""
        LEFT JOIN project_{project_name}.exported_attributes AS ex
        ON folders.parent_id = ex.folder_id
        """,
        f"""
        INNER JOIN public.projects AS pr
        ON pr.name ILIKE '{project_name}'
        """,
    ]
    sql_group_by = ["folders.id", "pr.attrib", "ex.attrib"]
    sql_conditions = []
    sql_having = []

    use_hierarchy = (
        (paths is not None)
        or (path_ex is not None)
        or fields.has_any("path", "parents")
    )

    access_list = await create_folder_access_list(root, info)

    if access_list is not None:
        sql_conditions.append(f"path like ANY ('{{ {','.join(access_list)} }}')")
        use_hierarchy = True

    # We need to use children-join
    if (has_children is not None) or fields.has_any("childount", "hasChildren"):
        sql_columns.append("COUNT(children.id) AS child_count")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.folders AS children
            ON folders.id = children.parent_id
            """
        )

    if (has_subsets is not None) or fields.has_any("subsetCount", "hasSubsets"):
        sql_columns.append("COUNT(subsets.id) AS subset_count")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.subsets AS subsets
            ON folders.id = subsets.folder_id
            """
        )

    if (has_tasks is not None) or fields.has_any("taskCount", "hasTasks"):
        sql_columns.append("COUNT(tasks.id) AS task_count")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.tasks AS tasks
            ON folders.id = tasks.folder_id
            """
        )

    # We need to join hierarchy view
    if use_hierarchy:
        sql_columns.append("hierarchy.path AS path")
        sql_group_by.append("hierarchy.path")
        sql_joins.append(
            f"""
            INNER JOIN project_{project_name}.hierarchy AS hierarchy
            ON folders.id = hierarchy.id
            """
        )

    #
    # Conditions
    #

    if ids:
        sql_conditions.append(f"folders.id IN {SQLTool.id_array(ids)}")

    if parent_id is not None:
        # Still used. do not remove!
        sql_conditions.append(
            "folders.parent_id IS NULL"
            if parent_id == "root"
            else f" folders.parent_id = '{EntityID.parse(parent_id)}'"
        )

    if parent_ids is not None:
        pids_set = set(parent_ids)
        lconds = []
        if "root" in pids_set or None in pids_set:
            pids_set.discard("root")
            pids_set.discard(None)  # type: ignore
            lconds.append("folders.parent_id IS NULL")

        if pids_set:
            lconds.append(f"folders.parent_id IN {SQLTool.id_array(list(pids_set))}")

        if lconds:
            sql_conditions.append(f"({ ' OR '.join(lconds) })")

    if folder_types is not None:
        validate_name_list(folder_types)
        sql_conditions.append(f"folders.folder_type in {SQLTool.array(folder_types)}")

    if name is not None:
        validate_name(name)
        sql_conditions.append(f"folders.name ILIKE '{name}'")

    if names is not None:
        validate_name_list(names)
        sql_conditions.append(f"folders.name in {SQLTool.array(names)}")

    if statuses:
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")

    if tags:
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if has_subsets is not None:
        sql_having.append(
            "COUNT(subsets.id) > 0" if has_subsets else "COUNT(subsets.id) = 0"
        )

    if has_children is not None:
        sql_having.append(
            "COUNT(children.id) > 0" if has_children else "COUNT(children.id) = 0"
        )

    if has_tasks is not None:
        sql_having.append("COUNT(tasks.id) > 0" if has_tasks else "COUNT(tasks.id) = 0")

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "folders.id", has_links)
        )

    if paths is not None:
        # TODO: sanitize
        sql_conditions.append(f"hierarchy.path IN {SQLTool.array(paths)}")

    if path_ex is not None:
        # TODO: sanitize
        sql_conditions.append(f"hierarchy.path ~ '{path_ex}'")

    if attributes:
        for attribute_input in attributes:
            if not attribute_library.is_valid("folder", attribute_input.name):
                continue
            values = [v.replace("'", "''") for v in attribute_input.values]
            sql_conditions.append(
                f"""
                (pr.attrib || coalesce(ex.attrib, '{{}}'::jsonb ) || folders.attrib)
                ->>'{attribute_input.name}' IN {SQLTool.array(values)}
                """
            )

    #
    # Pagination
    #

    order_by = ["folders.creation_order"]

    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"folders.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    paging_fields = FieldInfo(info, ["folders"])
    need_cursor = paging_fields.has_any(
        "folders.pageInfo.startCursor",
        "folders.pageInfo.endCursor",
        "folders.edges.cursor",
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
        FROM project_{project_name}.folders AS folders
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        GROUP BY {",".join(sql_group_by)}
        {SQLTool.conditions(sql_having).replace("WHERE", "HAVING", 1)}
        {pagination}
    """

    return await resolve(
        FoldersConnection,
        FolderEdge,
        FolderNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_folder(root, info: Info, id: str) -> FolderNode | None:
    """Return a folder node based on its ID"""
    if not id:
        return None
    connection = await get_folders(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
