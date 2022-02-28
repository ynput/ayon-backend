"""[GET] /projects (List projects)"""

import time
from typing import List, Literal, Optional

from fastapi import Depends, Query
from pydantic import BaseModel, Field

from openpype.api import dep_current_user
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool

from .router import router


class ListProjectsItemModel(BaseModel):
    name: str = Field(..., title="Project name")
    createdAt: int = Field(..., title="Creation time")
    updatedAt: int = Field(..., title="Last modified time")


class ListProjectsResponseModel(BaseModel):
    detail: str = Field("OK", example="Showing LENGTH of COUNT projects")
    count: int = Field(
        0, description="Total count of projects (regardless the pagination)", example=1
    )
    projects: List[ListProjectsItemModel] = Field(
        [],
        description="List of projects",
        example=[
            ListProjectsItemModel(
                name="Example project",
                createdAt=int(time.time()),
                updatedAt=int(time.time()),
            )
        ],
    )


@router.get(
    "/projects",
    response_model=ListProjectsResponseModel,
)
async def list_projects(
    user: UserEntity = Depends(dep_current_user),
    page: int = Query(1, title="Page", ge=1),
    length: int = Query(
        50,
        title="Records per page",
        description="If not provided, the result will not be limited",
        ge=1,
    ),
    library: Optional[bool] = Query(
        None,
        title="Show library projects",
        description="If not provided, return projects regardless the flag",
    ),
    active: Optional[bool] = Query(
        None,
        title="Show active projects",
        description="If not provided, return projects regardless the flag",
    ),
    order: Literal["name", "createdAt", "updatedAt"] = Query(
        "name", title="Attribute to order the list by"
    ),
    desc: Optional[bool] = Query(False, title="Sort in descending order"),
    name: Optional[str] = Query(
        "",
        title="Filter by name",
        description="""Limit the result to project with the matching name,
        or its part. % character may be used as a wildcard""",
        example="forest",
    ),
):
    """
    Return a list of available projects.
    """

    count = 0
    projects = []
    conditions = []

    if library is not None:
        conditions.append("library IS " + "TRUE" if library else "FALSE")
    if active is not None:
        conditions.append("archived IS " + "TRUE" if active else "FALSE")

    if name:
        # TODO: sanitize SQL injection
        conditions.append(f"name ILIKE '{name}'")

    for row in await Postgres.fetch(
        f"""
            SELECT
                COUNT(name) OVER () AS count,
                name,
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
        projects.append(
            ListProjectsItemModel(
                name=row["name"],
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
