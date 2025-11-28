import json
from typing import Annotated

from ayon_server.access.access_groups import AccessGroups
from ayon_server.access.utils import path_to_paths
from ayon_server.entities import ProjectEntity
from ayon_server.entities.core import attribute_library
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import TasksConnection
from ayon_server.graphql.edges import TaskEdge
from ayon_server.graphql.nodes.task import TaskNode
from ayon_server.graphql.resolvers.common import (
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
from ayon_server.graphql.types import Info
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import (
    sanitize_string_list,
    validate_name_list,
    validate_status_list,
    validate_type_name_list,
    validate_user_name_list,
)
from ayon_server.utils import SQLTool, slugify

from .pagination import create_pagination
from .sorting import (
    get_attrib_sort_case,
    get_status_sort_case,
    get_task_types_sort_case,
)

SORT_OPTIONS = {
    "name": "tasks.name",
    "taskType": "tasks.task_type",
    "assignees": "array_to_string(tasks.assignees, '')",
    "status": "tasks.status",
    "createdAt": "tasks.created_at",
    "updatedAt": "tasks.updated_at",
    "createdBy": "tasks.created_by",
    "updatedBy": "tasks.updated_by",
}


class FullAccess(Exception):
    pass


async def create_task_acl(
    project_name: str, access_group_names: list[str]
) -> tuple[set[str], bool]:
    """Get the access control list for tasks based on access groups.

    - set of folder paths we have full access to
    - bool indicating if we have 'assigned' access

    raises FullAccess if we have full access to all tasks

    """

    full_access = set()
    assigned_access: bool = False

    for ag_name in access_group_names:
        if (ag_name, project_name) in AccessGroups.access_groups:
            ag_perms = AccessGroups.access_groups[(ag_name, project_name)]
        elif (ag_name, "_") in AccessGroups.access_groups:
            ag_perms = AccessGroups.access_groups[(ag_name, "_")]
        else:
            continue
        read_perms = ag_perms.read
        if not read_perms.enabled:
            # we have an access group that does not restrict read access,
            # so we have full access
            raise FullAccess()
        for acl in read_perms.access_list:
            if acl.access_type == "assigned":
                assigned_access = True
                continue

            if acl.path is None:
                # make linter happy. path is nullable only for 'assigned' type
                continue

            for p in path_to_paths(acl.path, True, True):
                full_access.add(p)

    return full_access, assigned_access


async def get_tasks(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    task_types: Annotated[
        list[str] | None,
        argdesc("List of task types to filter by"),
    ] = None,
    folder_ids: Annotated[
        list[str] | None,
        argdesc("List of parent folder IDs to filter by"),
    ] = None,
    attributes: Annotated[
        list[AttributeFilterInput] | None,
        argdesc("Filter by a list of attributes"),
    ] = None,
    names: Annotated[
        list[str] | None,
        argdesc("List of names to filter by"),
    ] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    has_links: ARGHasLinks = None,
    assignees: Annotated[
        list[str] | None,
        argdesc(
            "List tasks with all of the provided assignees. "
            "Empty list will return tasks with no assignees."
        ),
    ] = None,
    assignees_any: Annotated[
        list[str] | None,
        argdesc(
            "List tasks with any of the provided assignees. "
            "Empty list will return tasks with any assignees."
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        argdesc(
            "List tasks with all of the provided tags. "
            "Empty list will return tasks with no tags."
        ),
    ] = None,
    tags_any: Annotated[
        list[str] | None,
        argdesc(
            "List tasks with any of the provided tags. "
            "Empty list will return tasks with any tags."
        ),
    ] = None,
    include_folder_children: Annotated[
        bool,
        argdesc("Include tasks in child folders when folderIds is used"),
    ] = False,
    search: Annotated[str | None, argdesc("Fuzzy text search filter")] = None,
    filter: Annotated[str | None, argdesc("Filter tasks using QueryFilter")] = None,
    folder_filter: Annotated[
        str | None, argdesc("Filter tasks by queryfilter on folders")
    ] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> TasksConnection:
    """Return a list of tasks."""

    if folder_ids == ["root"] or info.context["user"].is_guest:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    project_name = root.project_name
    project = await ProjectEntity.load(project_name)
    fields = FieldInfo(info, ["tasks.edges.node", "task"])
    use_folder_query = False

    #
    # SQL
    #

    sql_cte = []
    sql_conditions = []

    sql_columns = [
        "tasks.*",
        "hierarchy.path AS _folder_path",
        "f_ex.attrib as parent_folder_attrib",
    ]

    sql_joins = [
        f"""
        INNER JOIN project_{project_name}.hierarchy AS hierarchy
        ON tasks.folder_id = hierarchy.id
        """,
        f"""
        INNER JOIN project_{project_name}.exported_attributes AS f_ex
        ON tasks.folder_id = f_ex.folder_id
        """,
    ]

    if fields.any_endswith("hasReviewables"):
        sql_cte.append(
            f"""
            reviewables AS (
                SELECT v.task_id AS task_id FROM project_{project_name}.activity_feed af
                INNER JOIN project_{project_name}.versions v
                ON af.entity_id = v.id
                AND af.entity_type = 'version'
                AND af.activity_type = 'reviewable'
            )
            """
        )

        sql_columns.append(
            "EXISTS (SELECT 1 FROM reviewables WHERE task_id = tasks.id) "
            "AS has_reviewables"
        )

    if ids is not None:
        if not ids:
            return TasksConnection()
        sql_conditions.append(f"tasks.id IN {SQLTool.id_array(ids)}")

    if folder_ids is not None:
        if not folder_ids:
            return TasksConnection()

        if include_folder_children:
            use_folder_query = True
            sql_cte.append(
                f"""
                top_folder_paths AS (
                    SELECT path FROM project_{project_name}.hierarchy
                    WHERE id IN {SQLTool.id_array(folder_ids)}
                )
                """
            )

            sql_cte.append(
                f"""
                child_folder_ids AS (
                    SELECT id FROM project_{project_name}.hierarchy
                    WHERE EXISTS (
                        SELECT 1
                        FROM top_folder_paths
                        WHERE project_{project_name}.hierarchy.path
                        LIKE top_folder_paths.path || '/%'
                    )
                    OR project_{project_name}.hierarchy.path = ANY (
                        SELECT path FROM top_folder_paths
                    )
                )
                """
            )
            sql_conditions.append(
                "tasks.folder_id IN (SELECT id FROM child_folder_ids)"
            )

        else:
            sql_conditions.append(f"tasks.folder_id IN {SQLTool.id_array(folder_ids)}")

    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"tasks.folder_id = '{root.id}'")

    if names is not None:
        if not names:
            return TasksConnection()
        validate_name_list(names)
        sql_conditions.append(f"tasks.name IN {SQLTool.array(names)}")

    if task_types is not None:
        if not task_types:
            return TasksConnection()
        validate_type_name_list(task_types)
        sql_conditions.append(f"tasks.task_type IN {SQLTool.array(task_types)}")

    if statuses is not None:
        if not statuses:
            return TasksConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"tasks.status IN {SQLTool.array(statuses)}")

    if tags is not None:
        if not tags:
            sql_conditions.append("tasks.tags = '{}'")
        else:
            tags = sanitize_string_list(tags)
            sql_conditions.append(f"tasks.tags @> {SQLTool.array(tags, curly=True)}")

    if tags_any is not None:
        if not tags_any:
            sql_conditions.append("tasks.tags != '{}'")
        else:
            tags_any = sanitize_string_list(tags_any)
            sql_conditions.append(
                f"tasks.tags && {SQLTool.array(tags_any, curly=True)}"
            )

    if assignees is not None:
        if not assignees:
            sql_conditions.append("tasks.assignees = '{}'")
        else:
            validate_user_name_list(assignees)
            sql_conditions.append(
                f"tasks.assignees @> {SQLTool.array(assignees, curly=True)}"
            )

    if assignees_any is not None:
        if not assignees_any:
            sql_conditions.append("tasks.assignees != '{}'")
        else:
            validate_user_name_list(assignees_any)
            sql_conditions.append(
                f"tasks.assignees && {SQLTool.array(assignees_any, curly=True)}"
            )

    if has_links is not None:
        sql_conditions.extend(get_has_links_conds(project_name, "tasks.id", has_links))

    user = info.context["user"]
    access_list = None
    if not user.is_manager:
        perms = user.permissions(project_name)

        if perms.advanced.show_sibling_tasks:
            access_list = await create_folder_access_list(root, info)
            if access_list is not None:
                sql_conditions.append(
                    f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
                )
        else:
            try:
                facl, assigned_access = await create_task_acl(
                    project_name,
                    user.data.get("accessGroups", {}).get(project_name, []),
                )
            except FullAccess:
                pass
            else:
                sql_acl_conds = []
                sql_acl_conds.append(
                    f"hierarchy.path like ANY ('{{ {','.join(facl)} }}')"
                )
                if assigned_access:
                    sql_acl_conds.append(
                        f"""tasks.assignees::text[] @> '{{{user.name}}}'"""
                    )

                if sql_acl_conds:
                    sql_conditions.append(f"({' OR '.join(sql_acl_conds)})")

    if attributes:
        for attribute_input in attributes:
            if not attribute_library.is_valid("task", attribute_input.name):
                continue
            values = [v.replace("'", "''") for v in attribute_input.values]
            sql_conditions.append(
                f"""
                (coalesce(f_ex.attrib, '{{}}'::jsonb ) || tasks.attrib)
                ->>'{attribute_input.name}' IN {SQLTool.array(values)}
                """
            )

    if filter:
        column_whitelist = [
            "active",
            "assignees",
            "attrib",
            "folder_id",
            "id",
            "label",
            "name",
            "status",
            "tags",
            "task_type",
            "thumbnail_id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        fdata = json.loads(filter)
        fq = QueryFilter(**fdata)
        # when filtering by attribute, we need to merge parent folder attributes
        # with the task attributes to get the full attribute set
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="tasks",
            column_map={
                "attrib": "(coalesce(f_ex.attrib, '{}'::jsonb ) || tasks.attrib)"
            },
        ):
            sql_conditions.append(fcond)

    if folder_filter:
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
        fdata = json.loads(folder_filter)
        fq = QueryFilter(**fdata)
        if fcond := build_filter(
            fq,
            column_whitelist=column_whitelist,
            table_prefix="folders",
            column_map={"attrib": "f_ex.attrib"},
        ):
            sql_conditions.append(fcond)
            use_folder_query = True

    if search:
        use_folder_query = True
        terms = slugify(search, make_set=True)
        # isn't it nice that slugify effectively prevents sql injections?
        for term in terms:
            cond = f"""(
            tasks.name ILIKE '%{term}%'
            OR tasks.label ILIKE '%{term}%'
            OR tasks.task_type ILIKE '%{term}%'
            OR hierarchy.path ILIKE '%{term}%'
            )"""
            sql_conditions.append(cond)

    #
    # Additional joins
    # Following joins have overhead, so only do them if needed
    #

    # Do we need the parent folder data?
    if use_folder_query or "folder" in fields:
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
                "folders.label AS _folder_label",
                "folders.folder_type AS _folder_folder_type",
                "folders.thumbnail_id AS _folder_thumbnail_id",
                "folders.parent_id AS _folder_parent_id",
                "folders.attrib AS _folder_attrib",
                "folders.data AS _folder_data",
                "folders.active AS _folder_active",
                "folders.status AS _folder_status",
                "folders.tags AS _folder_tags",
                "folders.created_at AS _folder_created_at",
                "folders.updated_at AS _folder_updated_at",
                "projects.attrib as _folder_project_attributes",
                "pf_ex.attrib as _folder_inherited_attributes",
            ]
        )

        # Use inner join, tasks without folder cannot exist

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.folders
                ON folders.id = tasks.folder_id
                """,
                # but not here. parent's parent can be NULL
                f"""
                LEFT JOIN project_{project_name}.exported_attributes AS pf_ex
                ON folders.parent_id = pf_ex.folder_id
                """,
                f"""
                INNER JOIN public.projects AS projects
                ON projects.name ILIKE '{project_name}'
                """,
            ]
        )

    #
    # Pagination
    #

    order_by = []
    if sort_by is not None:
        if sort_by == "taskType":
            task_type_case = get_task_types_sort_case(project)
            order_by.append(task_type_case)
        elif sort_by == "status":
            status_type_case = get_status_sort_case(project, "tasks.status")
            order_by.append(status_type_case)
        elif sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by == "path":
            order_by = ["hierarchy.path", "tasks.name"]
        elif sort_by.startswith("attrib."):
            attr_name = sort_by[7:]
            exp = "(f_ex.attrib || tasks.attrib)"
            attr_case = await get_attrib_sort_case(attr_name, exp)
            order_by.insert(0, attr_case)
        else:
            raise BadRequestException(f"Invalid sort_by value: {sort_by}")

    if not order_by:
        # If no sorting specified, use creation order to have stable sorting
        # as the requester doesn't care about the order in this case.
        order_by.append("tasks.creation_order")

    elif len(order_by) < 2:
        # If a single sort criteria is specified, add a secondary sort by name
        # to have stable sorting when multiple items have the same value
        # In this case we don't want to use creation order as secondary sort,
        # because sorting is mainly invoked from the GUI and path makes more sense
        order_by.append("hierarchy.path || '/' || tasks.name")

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

    sql_columns.insert(0, cursor)
    sql_columns_str = ",\n".join(sql_columns)

    query = f"""
{cte}
SELECT
{sql_columns_str}
FROM project_{project_name}.tasks AS tasks
{" ".join(sql_joins)}
{SQLTool.conditions(sql_conditions)}
{ordering}
    """

    # Keep it here for debugging :)
    # from ayon_server.logging import logger
    #
    # logger.debug(f"Task query\n{query}")

    return await resolve(
        TasksConnection,
        TaskEdge,
        TaskNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_task(root, info: Info, id: str) -> TaskNode:
    """Return a task node based on its ID"""
    if not id:
        raise BadRequestException("Task ID not specified")
    connection = await get_tasks(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Task not found")
    return connection.edges[0].node
