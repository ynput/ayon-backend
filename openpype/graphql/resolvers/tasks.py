from typing import Annotated

from strawberry.types import Info

from openpype.graphql.connections import TasksConnection
from openpype.graphql.edges import TaskEdge
from openpype.graphql.nodes.task import TaskNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
)
from openpype.types import validate_name_list
from openpype.utils import SQLTool


async def get_tasks(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    task_types: Annotated[
        list[str] | None, argdesc("List of task types to filter by")
    ] = None,
    folder_ids: Annotated[
        list[str] | None, argdesc("List of parent folder IDs to filter by")
    ] = None,
#    name: Annotated[str | None, argdesc("Text string to filter name by")] = None,
    names: Annotated[list[str] | None, argdesc("List of names to filter by")] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
) -> TasksConnection:
    """Return a list of tasks."""

    if folder_ids == ["root"]:
        # this is a workaround to allow selecting tasks along with children folders
        # in a single query of the manager page.
        # (assuming the root element of the project cannot have tasks :) )
        return TasksConnection(edges=[])

    project_name = root.project_name
    fields = FieldInfo(info, ["tasks.edges.node", "subset"])

    #
    # SQL
    #

    sql_columns = [
        "tasks.id AS id",
        "tasks.name AS name",
        "tasks.folder_id AS folder_id",
        "tasks.task_type AS task_type",
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

    if ids:
        sql_conditions.append(f"tasks.id IN {SQLTool.id_array(ids)}")

    if folder_ids:
        sql_conditions.append(f"tasks.folder_id IN {SQLTool.id_array(folder_ids)}")
    elif root.__class__.__name__ == "FolderNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"tasks.folder_id = '{root.id}'")

    # if name:
    #     sql_conditions.append(f"tasks.name ILIKE '{name}'")

    if names:
        validate_name_list(names)
        sql_conditions.append(f"tasks.name IN {SQLTool.array(names)}")

    if task_types:
        validate_name_list(task_types)
        sql_conditions.append(f"tasks.task_type IN {SQLTool.array(task_types)}")

    if tags:
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if has_links is not None:
        sql_conditions.extend(get_has_links_conds(project_name, "tasks.id", has_links))

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

    #
    # Joins
    #

    if "attrib" in fields:
        sql_columns.append("pf.attrib as parent_folder_attrib")
        sql_joins.append(
            f"""
            LEFT JOIN project_{project_name}.exported_attributes AS pf
            ON tasks.folder_id = pf.folder_id
            """
        )
    else:
        sql_columns.append("'{}'::JSONB as parent_folder_attrib")

    if "folder" in fields or (access_list is not None):
        sql_columns.extend(
            [
                "folders.id AS _folder_id",
                "folders.name AS _folder_name",
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
            f"""
            INNER JOIN project_{project_name}.folders
            ON folders.id = tasks.folder_id
            """
        )

        if any(
            field.endswith("folder.path") or field.endswith("folder.parents")
            for field in fields
        ) or (access_list is not None):
            sql_columns.append("hierarchy.path AS _folder_path")
            sql_joins.append(
                f"""
                LEFT JOIN project_{project_name}.hierarchy AS hierarchy
                ON folders.id = hierarchy.id
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

    #
    # Pagination
    #

    order_by = "tasks.creation_order"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {", ".join(sql_columns)}
        FROM project_{project_name}.tasks AS tasks
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        TasksConnection,
        TaskEdge,
        TaskNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
        order_by=order_by,
    )


async def get_task(root, info: Info, id: str) -> TaskNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_tasks(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
