"""[GET] /projects (List projects)"""

from datetime import datetime
from typing import Literal

from fastapi import Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel
from ayon_server.utils import SQLTool
from projects.router import router


class ListProjectsItemModel(OPModel):
    name: str = Field(..., title="Project name")
    code: str = Field(..., title="Project code")
    createdAt: datetime = Field(..., title="Creation time")
    updatedAt: datetime = Field(..., title="Last modified time")


class ListProjectsResponseModel(OPModel):
    detail: str = Field("OK", example="Showing LENGTH of COUNT projects")
    count: int = Field(
        0, description="Total count of projects (regardless the pagination)", example=1
    )
    projects: list[ListProjectsItemModel] = Field(
        [],
        description="List of projects",
        example=[
            ListProjectsItemModel(
                name="Example project",
                code="ex",
                createdAt=datetime.now().isoformat(),
                updatedAt=datetime.now().isoformat(),
            )
        ],
    )


@router.get("/projects")
async def list_projects(
    user: CurrentUser,
    page: int = Query(1, title="Page", ge=1),
    length: int = Query(
        50,
        title="Records per page",
        description="If not provided, the result will not be limited",
        ge=1,
    ),
    library: bool
    | None = Query(
        None,
        title="Show library projects",
        description="If not provided, return projects regardless the flag",
    ),
    active: bool
    | None = Query(
        None,
        title="Show active projects",
        description="If not provided, return projects regardless the flag",
    ),
    order: Literal["name", "createdAt", "updatedAt"] = Query(
        "name", title="Attribute to order the list by"
    ),
    desc: bool = Query(False, title="Sort in descending order"),
    name: str
    | None = Query(
        None,
        title="Filter by name",
        description="""Limit the result to project with the matching name,
        or its part. % character may be used as a wildcard""",
        example="forest",
        regex=NAME_REGEX,
    ),
) -> ListProjectsResponseModel:
    """
    Return a list of available projects.
    """

    count = 0
    projects = []
    conditions = []

    if library is not None:
        conditions.append(f"library IS {'TRUE' if library else 'FALSE'}")
    if active is not None:
        conditions.append(f"active IS {'TRUE' if active else 'FALSE'}")

    if name:
        conditions.append(f"name ILIKE '{name}'")

    for row in await Postgres.fetch(
        f"""
            SELECT
                COUNT(name) OVER () AS count,
                name,
                code,
                created_at,
                updated_at
            FROM projects
            {SQLTool.conditions(conditions)}
            {SQLTool.order(
                (order if order in ["name"] else ""),
                desc,
                length,
                max(0, (page-1)*length)
            )}
        """,
    ):
        count = row["count"]

        # TODO: skipping projects based on permissions
        # breaks the pagination. Remove pagination completely?
        # Or rather use graphql-like approach with cursor?
        if not user.is_manager:
            access_groups = user.data.get("accessGroups", {})
            if not isinstance(access_groups, dict):
                continue
            if not access_groups.get(row["name"]):
                continue

        projects.append(
            ListProjectsItemModel(
                name=row["name"],
                code=row["code"],
                createdAt=row["created_at"],
                updatedAt=row["updated_at"],
            )
        )

    if not projects:
        # No project is found (this includes the case
        # where the page is out of range)
        return ListProjectsResponseModel(detail="No projects", count=count)

    return ListProjectsResponseModel(
        detail=f"Showing {len(projects)} of {count} projects)",
        count=count,
        projects=projects,
    )
