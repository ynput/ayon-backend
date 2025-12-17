import json
from typing import Annotated

from ayon_server.entities import ProjectEntity
from ayon_server.entities.core import attribute_library
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import FoldersConnection
from ayon_server.graphql.edges import FolderEdge
from ayon_server.graphql.nodes.folder import FolderNode
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import (
    validate_name,
    validate_name_list,
    validate_status_list,
    validate_type_name_list,
)
from ayon_server.utils import EntityID, SQLTool, slugify

from .common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    AttributeFilterInput,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from .pagination import create_pagination
from .sorting import (
    get_attrib_sort_case,
    get_folder_types_sort_case,
    get_status_sort_case,
)

SORT_OPTIONS = {
    "name": "folders.name",
    "createdAt": "folders.created_at",
    "updatedAt": "folders.updated_at",
    "createdBy": "folders.created_by",
    "updatedBy": "folders.updated_by",
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
        list[AttributeFilterInput] | None, argdesc("Filter by a list of attributes")
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
    assignees: Annotated[
        list[str] | None,
        argdesc("List folders with tasks assigned to these users"),
    ] = None,
    has_children: Annotated[
        bool | None, argdesc("Whether to filter by folders with children")
    ] = None,
    has_products: Annotated[
        bool | None, argdesc("Whether to filter by folders with products")
    ] = None,
    has_tasks: Annotated[
        bool | None, argdesc("Whether to filter by folders with tasks")
    ] = None,
    has_links: ARGHasLinks = None,
    search: Annotated[str | None, argdesc("Fuzzy text search filter")] = None,
    filter: Annotated[str | None, argdesc("Filter folders using QueryFilter")] = None,
    task_filter: Annotated[str | None, argdesc("Fitler folders by tasks")] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> FoldersConnection:
    """Return a list of folders."""

    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    fields = FieldInfo(info, ["folders.edges.node", "folder"])

    if info.context["user"].is_guest:
        return FoldersConnection(edges=[])

    #
    # SQL
    #

    sql_cte = []
    sql_columns = [
        "folders.*",
        "hierarchy.path AS path",
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
        f"""
        INNER JOIN project_{project_name}.hierarchy AS hierarchy
        ON folders.id = hierarchy.id
        """,
    ]
    sql_group_by = ["folders.id", "pr.attrib", "ex.attrib", "hierarchy.path"]
    sql_conditions = []
    sql_having = []

    access_list = await create_folder_access_list(root, info)

    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

    # We need to use children-join
    if (has_children is not None) or fields.has_any("childount", "hasChildren"):
        sql_columns.append("COUNT(children.id) AS child_count")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.folders AS children
            ON folders.id = children.parent_id
            """
        )

    if (has_products is not None) or fields.has_any("productCount", "hasProducts"):
        sql_columns.append("COUNT(products.id) AS product_count")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.products AS products
            ON folders.id = products.folder_id
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

    if fields.any_endswith("hasReviewables"):
        sql_cte.append(
            f"""
            reviewables AS (
                SELECT p.folder_id AS folder_id
                FROM project_{project_name}.activity_feed af
                INNER JOIN project_{project_name}.versions v
                ON af.entity_id = v.id
                AND af.entity_type = 'version'
                AND  af.activity_type = 'reviewable'
                INNER JOIN project_{project_name}.products p
                ON p.id = v.product_id
            )
            """
        )

        sql_columns.append("(r.folder_id IS NOT NULL)::BOOLEAN AS has_reviewables")

        sql_joins.append(
            """
            LEFT JOIN reviewables r
            ON r.folder_id = folders.id
            """
        )

        sql_group_by.append("r.folder_id")

    if fields.any_endswith("hasVersions"):
        sql_columns.append("(fwv.ancestor_id IS NOT NULL)::BOOLEAN AS has_versions")

        sql_cte.extend(
            [
                f"""
            folder_closure AS (
                SELECT id AS ancestor_id, id AS descendant_id
                FROM project_{project_name}.folders
                UNION ALL
                SELECT fc.ancestor_id, f.id AS descendant_id
                FROM folder_closure fc
                JOIN project_{project_name}.folders f
                ON f.parent_id = fc.descendant_id
            )
            """,
                f"""
            folder_with_versions AS (
                SELECT DISTINCT fc.ancestor_id
                FROM folder_closure fc
                JOIN project_{project_name}.products p ON p.folder_id = fc.descendant_id
                JOIN project_{project_name}.versions v ON v.product_id = p.id
            )
            """,
            ]
        )

        sql_joins.append(
            """
            LEFT JOIN folder_with_versions fwv
            ON fwv.ancestor_id = folders.id
            """
        )

        sql_group_by.append("fwv.ancestor_id")

    #
    # Conditions
    #

    if ids is not None:
        if not ids:
            return FoldersConnection()
        sql_conditions.append(f"folders.id IN {SQLTool.id_array(ids)}")

    if parent_id is not None:
        # Still used. do not remove!
        sql_conditions.append(
            "folders.parent_id IS NULL"
            if parent_id == "root"
            else f" folders.parent_id = '{EntityID.parse(parent_id)}'"
        )

    if parent_ids is not None:
        if not parent_ids:
            return FoldersConnection()
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
        if not folder_types:
            return FoldersConnection()
        validate_type_name_list(folder_types)
        sql_conditions.append(f"folders.folder_type in {SQLTool.array(folder_types)}")

    if name is not None:
        validate_name(name)
        sql_conditions.append(f"folders.name ILIKE '{name}'")

    if names is not None:
        if not names:
            return FoldersConnection()
        validate_name_list(names)
        sql_conditions.append(f"folders.name in {SQLTool.array(names)}")

    if statuses is not None:
        if not statuses:
            return FoldersConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")

    if tags:
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if has_products is not None:
        sql_having.append(
            "COUNT(products.id) > 0" if has_products else "COUNT(products.id) = 0"
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
        if not paths:
            return FoldersConnection()
        paths = [p.strip("/").replace("'", "''") for p in paths]
        sql_conditions.append(f"hierarchy.path IN {SQLTool.array(paths)}")

    if path_ex is not None:
        path_ex = path_ex.replace("'", "''")
        sql_conditions.append(f"'/' || hierarchy.path ~ '{path_ex}'")

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

    if assignees is not None:
        validate_name_list(assignees)
        cond = f"""
            folders.id IN (
                SELECT folder_id FROM project_{project_name}.tasks
                WHERE assignees @> {SQLTool.array(assignees, curly=True)}
            )
        """
        sql_conditions.append(cond)

    if search:
        terms = slugify(search, make_set=True)
        for term in terms:
            term = term.replace("'", "''")
            sql_conditions.append(
                f"(folders.name ILIKE '%{term}%' OR "
                f"folders.label ILIKE '%{term}%' OR "
                f"hierarchy.path ILIKE '%{term}%')"
            )

    #
    # Filter
    #

    if filter:
        column_whitelist = [
            "id",
            "name",
            "label",
            "folder_type",
            "parent_id",
            "attrib",
            "data",
            "active",
            "status",
            "tags",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="folders",
            column_map={
                "attrib": "(pr.attrib || coalesce(ex.attrib, '{{}}'::jsonb ) || folders.attrib)",  # noqa: E501
            },
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

        fdate = json.loads(task_filter)
        fq = QueryFilter(**fdate)
        tfilter = build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="tasks",
        )

        if tfilter:
            sql_cte.append(
                f"""
                filtered_tasks AS (
                    SELECT DISTINCT folder_id
                    FROM project_{project_name}.tasks
                    WHERE {tfilter}
                )
                """
            )

            sql_joins.append(
                """
                INNER JOIN filtered_tasks ft
                ON ft.folder_id = folders.id
                """
            )

    #
    # Pagination
    #

    order_by = []

    if sort_by is not None:
        if sort_by == "folderType":
            folder_type_case = get_folder_types_sort_case(project)
            order_by.append(folder_type_case)
        elif sort_by == "status":
            status_type_case = get_status_sort_case(project, "folders.status")
            order_by.append(status_type_case)
        elif sort_by in SORT_OPTIONS:
            order_by.append(SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            exp = "(coalesce(ex.attrib, '{}'::JSONB) || folders.attrib)"
            attr_case = await get_attrib_sort_case(attr_name, exp)
            order_by.append(attr_case)
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    if not order_by:
        # If no sorting specified, use creation order to have stable sorting
        # as the requester doesn't care about the order in this case.
        order_by.append("folders.creation_order")

    elif len(order_by) < 2:
        # If a single sort criteria is specified, add a secondary sort by name
        # to have stable sorting when multiple items have the same value
        # In this case we don't want to use creation order as secondary sort,
        # because sorting is mainly invoked from the GUI and path makes more sense
        order_by.append("hierarchy.path")

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
        cte = f"WITH RECURSIVE {cte}"
    else:
        cte = ""

    query = f"""
        {cte}
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.folders AS folders
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        GROUP BY {",".join(sql_group_by)}
        {SQLTool.conditions(sql_having).replace("WHERE", "HAVING", 1)}
        {ordering}
    """
    # Keep it here for debugging :)
    # from ayon_server.logging import logger
    #
    # logger.debug(f"Folder query\n{query}")

    return await resolve(
        FoldersConnection,
        FolderEdge,
        FolderNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_folder(root, info: Info, id: str) -> FolderNode:
    """Return a folder node based on its ID"""
    if not id:
        raise BadRequestException("Folder ID is not specified")
    connection = await get_folders(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Folder not found")
    return connection.edges[0].node
