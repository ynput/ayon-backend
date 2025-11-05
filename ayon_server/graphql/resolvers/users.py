from typing import Annotated

from ayon_server.config import ayonconfig
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.graphql.connections import UsersConnection
from ayon_server.graphql.edges import UserEdge
from ayon_server.graphql.nodes.user import UserNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    resolve,
)
from ayon_server.graphql.resolvers.pagination import create_pagination
from ayon_server.graphql.types import Info
from ayon_server.types import (
    validate_email_list,
    validate_name_list,
    validate_user_name,
)
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
    emails: Annotated[
        list[str] | None,
        argdesc(
            """
            The emails of the users to retrieve.
            """
        ),
    ] = None,
    project_name: Annotated[
        str | None, argdesc("List only users assigned to a given project")
    ] = None,
    projects: Annotated[
        list[str] | None, argdesc("List only users assigned to projects")
    ] = None,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
) -> UsersConnection:
    """Return a list of users."""

    user = info.context["user"]
    if project_name is None and projects is None:
        user.check_permissions("studio.list_all_users")

    if user.is_guest:
        # TODO: allow listing users assigned to the same project?
        return UsersConnection(edges=[])

    # Filter by name

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

    if emails is not None:
        if not emails:
            return UsersConnection()
        validate_email_list(emails)
        emails = [e.lower() for e in emails]
        sql_conditions.append(
            f"LOWER(users.attrib->>'email') IN {SQLTool.array(emails)}"
        )

    # Filter by project

    if projects is None:
        projects = []
    if project_name and project_name not in projects:
        projects.append(project_name)

    info.context["user_project_list"] = projects

    if projects:
        validate_name_list(projects)

        cnd1 = "users.data->>'isAdmin' = 'true'"
        cnd2 = "users.data->>'isManager' = 'true'"

        cnd3l = []
        for pname in projects:
            xlist = ""
            if ayonconfig.limit_user_visibility and not user.is_manager:
                user_groups = user.data.get("accessGroups", {}).get(pname, [])
                ug_arr = SQLTool.array(user_groups, curly=True)
                xlist = f" AND (users.data->'accessGroups'->'{pname}' ?| {ug_arr})"
            cnd3l.append(f"(users.data->'accessGroups' ? '{pname}' {xlist})")

        cnd3 = " OR ".join(cnd3l)

        cnd = f"({cnd1} OR {cnd2} OR ({cnd3}))"
        sql_conditions.append(cnd)

    #
    # Pagination
    #

    order_by = ["name"]
    ordering, paging_conds, cursor = create_pagination(
        order_by, first, after, last, before
    )
    sql_conditions.append(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, * FROM public.users
        {SQLTool.conditions(sql_conditions)}
        {ordering}
    """

    return await resolve(
        UsersConnection,
        UserEdge,
        UserNode,
        query,
        first=first,
        last=last,
        context=info.context,
        order_by=order_by,
    )


async def get_user(root, info: Info, name: str) -> UserNode:
    """Return a project node based on its name."""
    if not name:
        raise BadRequestException("User name not specified")
    connection = await get_users(root, info, name=name)
    if not connection.edges:
        raise NotFoundException("User not found")
    return connection.edges[0].node
