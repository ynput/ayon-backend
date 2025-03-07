import json
from typing import Annotated

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
    create_pagination,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.graphql.types import Info
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import (
    sanitize_string_list,
    validate_name_list,
    validate_status_list,
    validate_user_name_list,
)
from ayon_server.utils import SQLTool, slugify

SORT_OPTIONS = {
    "name": "tasks.name",
    "status": "tasks.status",
    "createdAt": "tasks.created_at",
    "updatedAt": "tasks.updated_at",
    "taskType": "tasks.folder_type",
    "assignees": "array_to_string(tasks.assignees, '')",
}


async def get_priority_case() -> str:
    attr = "priority"
    res = await Postgres.fetch(
        "SELECT data->'enum' as enum FROM attributes where name = $1", attr
    )
    if not res or not res[0]["enum"]:
        return f"(pf.attrib || tasks.attrib)->>'{attr}'"
    case = "CASE"
    i = 0
    for i, eval in enumerate(res[0]["enum"]):
        e = eval["value"]
        case += f" WHEN (pf.attrib || tasks.attrib)->>'{attr}' = '{e}' THEN {i}"
    case += f" ELSE {i+1}"
    case += " END"
    return case


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
    includeFolderChildren: Annotated[
        bool,
        argdesc("Include tasks in child folders when folderIds is used"),
    ] = False,
    search: Annotated[str | None, argdesc("Fuzzy text search filter")] = None,
    filter: Annotated[str | None, argdesc("Filter tasks using QueryFilter")] = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> TasksConnection:
    """Return a list of tasks."""

    if folder_ids == ["root"]:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    project_name = root.project_name
    fields = FieldInfo(info, ["tasks.edges.node", "task"])

    use_folder_query = False

    #
    # SQL
    #

    sql_cte = []
    sql_columns = [
        "tasks.id AS id",
        "tasks.name AS name",
        "tasks.label AS label",
        "tasks.folder_id AS folder_id",
        "tasks.task_type AS task_type",
        "tasks.thumbnail_id AS thumbnail_id",
        "tasks.assignees AS assignees",
        "tasks.attrib AS attrib",
        "tasks.data AS data",
        "tasks.status AS status",
        "tasks.tags AS tags",
        "tasks.active AS active",
        "tasks.created_at AS created_at",
        "tasks.updated_at AS updated_at",
        "tasks.creation_order AS creation_order",
    ]
    sql_conditions = []
    sql_joins = []

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

        if includeFolderChildren:
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

    # if name:
    #     sql_conditions.append(f"tasks.name ILIKE '{name}'")

    if names is not None:
        if not names:
            return TasksConnection()
        validate_name_list(names)
        sql_conditions.append(f"tasks.name IN {SQLTool.array(names)}")

    if task_types is not None:
        if not task_types:
            return TasksConnection()
        validate_name_list(task_types)
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

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

    if attributes:
        for attribute_input in attributes:
            if not attribute_library.is_valid("task", attribute_input.name):
                continue
            values = [v.replace("'", "''") for v in attribute_input.values]
            sql_conditions.append(
                f"""
                (coalesce(pf.attrib, '{{}}'::jsonb ) || tasks.attrib)
                ->>'{attribute_input.name}' IN {SQLTool.array(values)}
                """
            )

    if filter:
        column_whitelist = [
            "id",
            "name",
            "folder_id",
            "task_type",
            "status",
            "tags",
            "assignees",
            "attrib",
            "data",
            "created_at",
            "updated_at",
            "active",
            "thumbnail_id",
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
                "attrib": "(coalesce(pf.attrib, '{}'::jsonb ) || tasks.attrib)"
            },
        ):
            sql_conditions.append(fcond)

    if search:
        terms = slugify(search, make_set=True)
        # isn't it nice that slugify effectively prevents sql injections?
        for term in terms:
            cond = f"""(
            tasks.name ILIKE '{term}%'
            OR tasks.label ILIKE '{term}%'
            OR tasks.task_type ILIKE '{term}%'
            OR hierarchy.path ILIKE '%{term}%'
            )"""
            sql_conditions.append(cond)

    #
    # Joins
    #

    # Do we need to join the parent folder's exported attributes?
    # We need it if we want to show the task attributes or filter by them
    if (
        attributes
        or filter
        or sort_by
        or fields.any_endswith("attrib")
        or fields.any_endswith("allAttrib")
    ):
        sql_columns.append("pf.attrib as parent_folder_attrib")
        sql_joins.append(
            f"LEFT JOIN project_{project_name}.exported_attributes AS pf "
            "ON tasks.folder_id = pf.folder_id\n"
        )
    else:
        # Otherwise, just return an empty JSONB object
        sql_columns.append("'{}'::JSONB as parent_folder_attrib")

    # Do we need the parent folder data?
    if "folder" in fields or (access_list is not None) or use_folder_query or search:
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
            ]
        )
        sql_joins.append(
            f"INNER JOIN project_{project_name}.folders "
            "ON folders.id = tasks.folder_id\n"
        )

        if (
            any(
                field.endswith("folder.path") or field.endswith("folder.parents")
                for field in fields
            )
            or (access_list is not None)
            or use_folder_query
            or search
        ):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"LEFT JOIN project_{project_name}.hierarchy AS hierarchy "
                "ON folders.id = hierarchy.id\n"
            )

        if any(field.endswith("folder.attrib") for field in fields):
            sql_columns.append("pr.attrib as _folder_project_attributes")
            sql_columns.append("ex.attrib as _folder_inherited_attributes")
            sql_joins.append(
                f"LEFT JOIN project_{project_name}.exported_attributes AS ex "
                "ON folders.parent_id = ex.folder_id\n",
            )
            sql_joins.append(
                f"INNER JOIN public.projects AS pr ON pr.name ILIKE '{project_name}'\n"
            )
        else:
            sql_columns.append("'{}'::JSONB as _folder_project_attributes")
            sql_columns.append("'{}'::JSONB as _folder_inherited_attributes")

    #
    # Pagination
    #

    order_by = ["tasks.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        if sort_by == "attrib.priority":
            priority_case = await get_priority_case()
            order_by.insert(0, priority_case)
        elif sort_by.startswith("attrib."):
            r = f"(pf.attrib || tasks.attrib)->'{sort_by[7:]}'"  # noqa
            order_by.insert(0, r)
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

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

    logger.debug(f"Task query\n{query}")

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
