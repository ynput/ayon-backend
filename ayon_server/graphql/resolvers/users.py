from typing import Annotated

from strawberry.types import Info

from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.connections import UsersConnection
from ayon_server.graphql.edges import UserEdge
from ayon_server.graphql.nodes.user import UserNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from ayon_server.types import validate_user_name
from ayon_server.utils import SQLTool


async def get_users(
    root,
    info: Info,
    name: Annotated[
        str | None,
        argdesc(
            """
            The name of the user to retrieve.
            """
        ),
    ] = None,
    names: Annotated[
        list[str] | None,
        argdesc(
            """
            The names of the users to retrieve.
            """
        ),
    ] = None,
    project_name: Annotated[
        str | None, argdesc("List only users assigned to a given project")
    ] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> UsersConnection:
    """Return a list of users."""

    user = info.context["user"]
    if (not user.is_manager) and (project_name is None):
        raise ForbiddenException("Only managers and administrators can view all users")

    sql_conditions = []
    if name is not None:
        validate_user_name(name)
        sql_conditions.append(f"users.name ILIKE '{name}'")

    if names is not None:
        if not names:
            return UsersConnection()
        for name in names:
            validate_user_name(name)
        sql_conditions.append(f"users.name IN {SQLTool.array(names)}")

    if project_name is not None:
        cnd1 = "users.data->>'isAdmin' = 'true'"
        cnd2 = "users.data->>'isManager' = 'true'"
        cnd3 = f"users.data->'accessGroups'->'{project_name}' IS NOT NULL"
        cnd = f"({cnd1} OR {cnd2} OR {cnd3})"
        sql_conditions.append(cnd)

    #
    # Pagination
    #

    order_by = ["name"]
    pagination, paging_conds, cursor = create_pagination(
        order_by, first, after, last, before
    )
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, * FROM users
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        UsersConnection,
        UserEdge,
        UserNode,
        None,
        query,
        first,
        last,
        context=info.context,
    )


async def get_user(root, info: Info, name: str) -> UserNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_users(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
