from typing import Annotated

from fastapi import APIRouter

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.types import Field, OPModel

router = APIRouter(tags=["Tasks"])


class TasksFoldersQuery(OPModel):
    pass


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


@router.post("/projects/{project_name}/tasksFolders")
async def query_tasks_folders(
    user: CurrentUser,
    project_name: ProjectName,
    query: TasksFoldersQuery,
) -> TasksFoldersResponse:
    result = []

    return TasksFoldersResponse(folder_ids=result)
