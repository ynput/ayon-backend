from typing import Annotated

from strawberry.types import Info

from openpype.graphql.connections import ProjectsConnection
from openpype.graphql.edges import ProjectEdge
from openpype.graphql.nodes.project import ProjectNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from openpype.utils import SQLTool, validate_name


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
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> ProjectsConnection:
    """Return a list of projects."""

    sql_conditions = []
    if name is not None:
        # if name is valid, it is also safe to use it in a query
        # without worrying about SQL injection
        if not validate_name(name):
            raise ValueError("Invalid project name specified")
        sql_conditions.append(f"projects.name ILIKE '{name}'")

    #
    # Pagination
    #

    order_by = "name"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    #
    #

    query = f"""
        SELECT * FROM projects
        {SQLTool.conditions(sql_conditions)}
        ORDER BY name
    """

    return await resolve(
        ProjectsConnection,
        ProjectEdge,
        ProjectNode,
        None,
        query,
        first,
        last,
        context=info.context,
        order_by="name",
    )


async def get_project(root, info: Info, name: str) -> ProjectNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_projects(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
