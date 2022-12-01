from typing import Annotated

from strawberry.types import Info

from openpype.exceptions import ForbiddenException
from openpype.graphql.connections import UsersConnection
from openpype.graphql.edges import UserEdge
from openpype.graphql.nodes.user import UserNode
from openpype.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    create_pagination,
    resolve,
)
from openpype.types import validate_name
from openpype.utils import SQLTool


async def get_users(
    root,
    info: Info,
    name: Annotated[
        str | None,
        argdesc(
            """
            The name of the user to retrieve.
            If not provided, all users will be returned.
            """
        ),
    ] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> UsersConnection:
    """Return a list of users."""

    user = info.context["user"]
    if not user.is_manager:
        raise ForbiddenException("Only managers and administrators can view users")

    sql_conditions = []
    if name is not None:
        validate_name(name)
        sql_conditions.append(f"users.name ILIKE '{name}'")

    #
    # Pagination
    #

    order_by = "name"
    pagination, paging_conds = create_pagination(order_by, first, after, last, before)
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT * FROM users
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
        order_by="name",
    )


async def get_user(root, info: Info, name: str) -> UserNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_users(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
