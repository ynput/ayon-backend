from typing import Annotated

from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import ProjectsConnection
from ayon_server.graphql.edges import ProjectEdge
from ayon_server.graphql.nodes.project import ProjectNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    FieldInfo,
    argdesc,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.types import validate_name
from ayon_server.utils import SQLTool


async def get_projects(
    root,
    info: Info,
    name: Annotated[
        str | None,
        argdesc(
            """
            The name of the project to retrieve.
            If not provided, all projects will be returned.
            """
        ),
    ] = None,
    code: Annotated[str | None, argdesc("The code of the project to retrieve.")] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> ProjectsConnection:
    """Return a list of projects."""

    sql_conditions = []
    if name is not None:
        validate_name(name)
        sql_conditions.append(f"projects.name ILIKE '{name}'")

    if code is not None:
        validate_name(code)
        sql_conditions.append(f"projects.code ILIKE '{code}'")

    fields = FieldInfo(info, ["projects.edges.node", "project"])

    cols = [
        "name",
        "code",
        "library",
        "attrib",
        "active",
        "created_at",
        "updated_at",
    ]

    if fields.has_any("config"):
        cols.append("config")

    if fields.has_any("data", "bundle") or info.context["user"].is_guest:
        cols.append("data")

    #
    # Pagination
    #

    order_by = ["name"]
    ordering, paging_conds, cursor = create_pagination(
        order_by, first, after, last, before
    )
    sql_conditions.append(paging_conds)
    cols.append(cursor)

    #
    # Query
    #

    query = f"""
        SELECT {', '.join(cols)}
        FROM public.projects
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    return await resolve(
        ProjectsConnection,
        ProjectEdge,
        ProjectNode,
        query,
        first=first,
        last=last,
        order_by=order_by,
        context=info.context,
    )


async def get_project(
    root,
    info: Info,
    name: str | None = None,
    code: str | None = None,
) -> ProjectNode:
    """Return a project node based on its name."""
    if not (name or code):
        raise BadRequestException("Either name or code must be provided.")
    connection = await get_projects(root, info, name=name, code=code)
    if not connection.edges:
        raise NotFoundException("Project not found")
    return connection.edges[0].node
