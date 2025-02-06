from typing import Annotated

from fastapi import APIRouter
from nxtools import logging

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel

router = APIRouter(tags=["Tasks"])


class TasksFoldersQuery(OPModel):
    filter: Annotated[QueryFilter | None, Field(description="")] = None


class TasksFoldersResponse(OPModel):
    folder_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="List of folder ids containing tasks matching the query",
            example=[
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ],
        ),
    ]


ALLOWED_KEYS = [
    "id",
    "name",
    "label",
    "status",
    "task_type",
    "assignees",
    "attrib",
    "active",
    "tags",
]


@router.post("/projects/{project_name}/tasksFolders")
async def query_tasks_folders(
    user: CurrentUser,
    project_name: ProjectName,
    request: TasksFoldersQuery,
) -> TasksFoldersResponse:
    result = []

    filter = build_filter(request.filter, key_whitelist=ALLOWED_KEYS)

    query = f"""
        SELECT DISTINCT folder_id
        FROM project_{project_name}.tasks
        WHERE
            {filter}
    """

    facl = await folder_access_list(user, project_name, "read")

    logging.debug("query", query)
    async for row in Postgres.iterate(query):
        if facl is not None and row["folder_id"] not in facl:
            continue
        result.append(row["folder_id"])

    return TasksFoldersResponse(folder_ids=result)
