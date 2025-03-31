from typing import Annotated

from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import RepresentationsConnection
from ayon_server.graphql.edges import RepresentationEdge
from ayon_server.graphql.nodes.representation import RepresentationNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    argdesc,
    create_folder_access_list,
    get_has_links_conds,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool


async def get_representations(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    version_ids: Annotated[
        list[str] | None, argdesc("List of parent version IDs to filter by")
    ] = None,
    # name: Annotated[str | None, argdesc("Text string to filter name by")] = None,
    names: Annotated[list[str] | None, argdesc("List of names to filter")] = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    has_links: ARGHasLinks = None,
) -> RepresentationsConnection:
    """Return a list of representations."""

    project_name = root.project_name

    #
    # Conditions
    #

    sql_columns = [
        "representations.id AS id",
        "representations.name AS name",
        "representations.version_id AS version_id",
        "representations.attrib AS attrib",
        "representations.status AS status",
        "representations.tags AS tags",
        "representations.active AS active",
        "representations.created_at AS created_at",
        "representations.updated_at AS updated_at",
        "representations.creation_order AS creation_order",
        "representations.files AS files",  # TODO: query conditionally
        "representations.data AS data",
        "representations.traits AS traits",
    ]

    sql_joins = []
    sql_conditions = []

    if ids is not None:
        if not ids:
            return RepresentationsConnection()
        sql_conditions.append(f"representations.id IN {SQLTool.id_array(ids)}")

    if version_ids is not None:
        if not version_ids:
            return RepresentationsConnection()
        sql_conditions.append(
            f"representations.version_id IN {SQLTool.id_array(version_ids)}"
        )
    elif root.__class__.__name__ == "VersionNode":
        # cannot use isinstance here because of circular imports
        sql_conditions.append(f"representations.version_id = '{root.id}'")

    if names is not None:
        if not names:
            return RepresentationsConnection()
        validate_name_list(names)
        sql_conditions.append(f"representations.name IN {SQLTool.array(names)}")

    if statuses is not None:
        if not statuses:
            return RepresentationsConnection()
        validate_status_list(statuses)
        sql_conditions.append(f"representations.status IN {SQLTool.array(statuses)}")

    if tags is not None:
        if not tags:
            return RepresentationsConnection()
        validate_name_list(tags)
        sql_conditions.append(
            f"representations.tags @> {SQLTool.array(tags, curly=True)}"
        )

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "representations.id", has_links)
        )

    #
    # ACL
    #

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.versions AS versions
                ON versions.id = representations.version_id
                """,
                f"""
                INNER JOIN project_{project_name}.products AS products
                ON products.id = versions.product_id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON hierarchy.id = products.folder_id
                """,
            ]
        )

    #
    # Pagination
    #

    order_by = ["representations.creation_order"]
    ordering, paging_conds, cursor = create_pagination(
        order_by, first, after, last, before
    )
    sql_conditions.append(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, {', '.join(sql_columns)}
        FROM project_{project_name}.representations
        {' '.join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    return await resolve(
        RepresentationsConnection,
        RepresentationEdge,
        RepresentationNode,
        query,
        project_name=project_name,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_representation(
    root,
    info: Info,
    id: str,
) -> RepresentationNode:
    """Return a representation node based on its ID"""
    if not id:
        raise BadRequestException("Folder ID is not specified")
    connection = await get_representations(root, info, ids=[id])
    if not connection.edges:
        raise NotFoundException("Representation not found")
    return connection.edges[0].node
