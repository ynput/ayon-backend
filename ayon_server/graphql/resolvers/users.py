from typing import Annotated

from ayon_server.config import ayonconfig
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.graphql.connections import UsersConnection
from ayon_server.graphql.edges import UserEdge
from ayon_server.graphql.nodes.user import UserNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGLast,
    argdesc,
    build_search_conditions,
    resolve,
    sortdesc,
)
from ayon_server.graphql.resolvers.field_stats import (
    MetricTargetInput,
    StatsAggregation,
    generate_field_stats,
    generate_specific_stats_columns,
)
from ayon_server.graphql.resolvers.pagination import (
    OrderBy,
    create_pagination,
    get_sort_keys,
    sort_columns,
    with_tiebreakers,
)
from ayon_server.graphql.types import Info
from ayon_server.types import (
    validate_email_list,
    validate_name_list,
    validate_user_name,
)
from ayon_server.utils import SQLTool

SORT_OPTIONS = {
    "name": "users.name",
    "fullName": "users.attrib->>'fullName'",
    "email": "users.attrib->>'email'",
}

# Only managers can see emails of other users (see UserNode)
MANAGER_ONLY_SORT_OPTIONS = {"email"}

# Fields are put into the SQL as they are, so only these are accepted
STATS_FIELDS = {"name", "attrib.fullName", "attrib.email"}
MANAGER_ONLY_STATS_FIELDS = {"attrib.email"}

# The fields are text, numeric and boolean aggregations would fail on them
STATS_AGGREGATIONS = {
    StatsAggregation.COUNT,
    StatsAggregation.FILLED,
    StatsAggregation.NOT_FILLED,
    StatsAggregation.PERCENTAGE_FILLED,
    StatsAggregation.PERCENTAGE_NOT_FILLED,
    StatsAggregation.DISTRIBUTION,
}


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
    is_support: Annotated[
        bool | None, argdesc("Deprecated: Filter users by isSupport flag in data")
    ] = None,
    search: Annotated[
        str | None,
        argdesc("Fuzzy text search filter (name, full name and email)"),
    ] = None,
    sort_by: Annotated[list[str] | None, sortdesc(SORT_OPTIONS)] = None,
    calculate_specific_statistics: Annotated[
        list[MetricTargetInput] | None,
        argdesc(
            """
            Statistics of the filtered users (e.g. COUNT of name) returned
            in fieldStats instead of the edges. Pagination is ignored.
            Fields: name, attrib.fullName, attrib.email (managers only).
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

    if search:
        search_columns = ["users.name", "users.attrib->>'fullName'"]
        # Only managers can see emails (see UserNode), so don't let
        # others probe them through the search
        if user.is_manager:
            search_columns.append("users.attrib->>'email'")
        if cond := build_search_conditions(search, search_columns):
            sql_conditions.append(cond)

    # Support users

    if not user.data.get("isSupport", False):
        sql_conditions.append("users.data->>'isSupport' IS DISTINCT FROM 'true'")

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
    # Statistics
    #

    if calculate_specific_statistics:
        _validate_stats_targets(calculate_specific_statistics, user.is_manager)
        if stats_select_clause := generate_specific_stats_columns(
            calculate_specific_statistics
        ):
            query = f"""
                WITH raw_data AS (
                    SELECT * FROM public.users
                    {SQLTool.conditions(sql_conditions)}
                )
                SELECT {stats_select_clause}
                FROM raw_data
            """
            field_stats = await generate_field_stats(query)
            return UsersConnection(edges=[], field_stats=field_stats)

    #
    # Pagination and sorting
    #

    order_by: OrderBy = []
    for sort_key, descending in get_sort_keys(sort_by):
        if sort_key not in SORT_OPTIONS:
            raise BadRequestException(f"Invalid sort_by value: {sort_key}")
        if sort_key in MANAGER_ONLY_SORT_OPTIONS and not user.is_manager:
            raise ForbiddenException(f"Only managers can sort users by {sort_key}")
        order_by.extend(sort_columns([SORT_OPTIONS[sort_key]], descending))

    # User names are unique, so sorting by name last
    # gives a stable order for the cursors
    order_by = with_tiebreakers(order_by, "users.name")

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


def _validate_stats_targets(targets: list[MetricTargetInput], is_manager: bool) -> None:
    for target in targets:
        if target.field not in STATS_FIELDS:
            raise BadRequestException(f"Invalid statistics field: {target.field}")
        if target.field in MANAGER_ONLY_STATS_FIELDS and not is_manager:
            raise ForbiddenException(
                f"Only managers can calculate statistics of {target.field}"
            )
        for aggregation in target.aggregations:
            if aggregation not in STATS_AGGREGATIONS:
                raise BadRequestException(
                    f"Invalid aggregation for {target.field}: {aggregation.value}"
                )
