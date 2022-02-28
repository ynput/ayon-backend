from typing import Annotated

from strawberry.types import Info

from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool, validate_name

from ..connections import UsersConnection
from ..edges import UserEdge
from ..nodes.user import UserNode
from .common import argdesc


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
    first: int | None = None,
    after: str | None = None,
    last: int | None = None,
    before: str | None = None,
) -> UsersConnection:
    """Return a list of users."""

    conditions = []
    if name is not None:
        # if name is valid, it is also safe to use it in a query
        # without worrying about SQL injection
        if not validate_name(name):
            raise ValueError("Invalid user name specified")
        conditions.append(f"users.name ILIKE '{name}'")

    return UsersConnection(
        edges=[
            UserEdge(node=UserNode.from_record(record))
            async for record in Postgres.iterate(
                f"""
                SELECT * FROM users
                {SQLTool.conditions(conditions)}
                """
            )
        ]
    )


async def get_user(root, info: Info, name: str) -> UserNode | None:
    """Return a project node based on its name."""
    if not name:
        return None
    connection = await get_users(root, info, name=name)
    if not connection.edges:
        return None
    return connection.edges[0].node
