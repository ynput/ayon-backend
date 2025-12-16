"""[GET] /projects (List projects)"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import Query

from ayon_server.api.dependencies import AllowGuests, CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel
from ayon_server.utils import SQLTool

from .router import router


class ListProjectsItemModel(OPModel):
    name: Annotated[str, Field(title="Project name")]
    code: Annotated[str, Field(title="Project code")]
    active: Annotated[bool, Field(title="Project is active")] = True
    library: Annotated[bool, Field(title="Project is a library project")] = False
    pinned: Annotated[bool, Field(title="Project is pinned")] = False
    project_folder: Annotated[str | None, Field(title="Project folder id")] = None
    created_at: Annotated[datetime, Field(title="Creation time")]
    updated_at: Annotated[datetime, Field(title="Last modified time")]


class ListProjectsResponseModel(OPModel):
    detail: Annotated[
        str,
        Field(
            example="Showing LENGTH of COUNT projects",
        ),
    ] = "OK"
    count: Annotated[
        int,
        Field(
            description="Total count of projects (regardless the pagination)",
            example=1,
        ),
    ] = 0
    projects: Annotated[
        list[ListProjectsItemModel],
        Field(
            description="List of projects",
            default_factory=list,
            example=[
                ListProjectsItemModel(
                    name="Example project",
                    code="ex",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    active=True,
                )
            ],
        ),
    ]


@router.get("/projects", dependencies=[AllowGuests])
async def list_projects(
    user: CurrentUser,
    page: Annotated[
        int,
        Query(
            title="Page",
            description="Page number, starting from 1",
            ge=1,
        ),
    ] = 1,
    length: Annotated[
        int | None,
        Query(
            title="Records per page",
            description="If not provided, the result will not be limited",
        ),
    ] = None,
    library: Annotated[
        bool | None,
        Query(
            title="Show library projects",
            description="If not provided, return projects regardless the flag",
        ),
    ] = None,
    active: Annotated[
        bool | None,
        Query(
            title="Show active projects",
            description="If not provided, return projects regardless the flag",
        ),
    ] = None,
    order: Annotated[
        Literal["name", "createdAt", "updatedAt"] | None,
        Query(
            title="Order by",
            description="Attribute to order the list by",
        ),
    ] = None,
    desc: Annotated[
        bool,
        Query(
            title="Sort in descending order",
        ),
    ] = False,
    name: Annotated[
        str | None,
        Query(
            title="Filter by name",
            description="""Limit the result to project with the matching name,
        or its part. % character may be used as a wildcard""",
            example="forest",
            regex=NAME_REGEX,
        ),
    ] = None,
) -> ListProjectsResponseModel:
    """
    Return a list of available projects.
    """

    count = 0
    projects = []
    conditions = []

    pinned = user.data.get("frontendPreferences", {}).get("pinnedProjects", [])

    if library is not None:
        conditions.append(f"library IS {'TRUE' if library else 'FALSE'}")
    if active is not None:
        conditions.append(f"active IS {'TRUE' if active else 'FALSE'}")

    if name:
        conditions.append(f"name ILIKE '{name}'")

    sql_order: str
    if order:
        sql_order = order
    else:
        sql_order = "active desc, name"

    length = length or None
    offset = max(0, (page - 1) * length) if length else None

    can_list_all_projects = False
    try:
        user.check_permissions("studio.create_projects")
        can_list_all_projects = True
    except Exception:
        pass

    for row in await Postgres.fetch(
        f"""
            SELECT
                COUNT(name) OVER () AS count,
                name,
                code,
                library,
                created_at,
                updated_at,
                active,
                data
            FROM projects
            {SQLTool.conditions(conditions)}
            {SQLTool.order(sql_order, desc, length, offset)}
        """,
    ):
        count = row["count"]

        if user.is_guest:
            # Evaluate guest before can_list_all_projects:
            # This is a security measure to prevent legacy
            # guest users from seeing all projects.
            guest_users = row["data"].get("guestUsers", {})
            if user.attrib.email not in guest_users:
                continue

        if not can_list_all_projects:
            access_groups = user.data.get("accessGroups", {})
            if not isinstance(access_groups, dict):
                continue
            if not access_groups.get(row["name"]):
                continue

        # TODO: skipping projects based on permissions
        # breaks the pagination. Remove pagination completely?
        # Or rather use graphql-like approach with cursor?

        projects.append(
            ListProjectsItemModel(
                name=row["name"],
                code=row["code"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                active=row.get("active", True),
                project_folder=row["data"].get("projectFolder"),
                library=row.get("library", False),
                pinned=row["name"] in pinned,
            )
        )

    if not projects:
        # No project is found (this includes the case
        # where the page is out of range)
        return ListProjectsResponseModel(
            detail="No projects",
            count=count,
            projects=[],
        )

    return ListProjectsResponseModel(
        detail=f"Showing {len(projects)} of {count} projects",
        count=count,
        projects=projects,
    )
