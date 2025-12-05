from typing import Annotated

from fastapi import APIRouter

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.exceptions import BadRequestException
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel
from ayon_server.utils import SQLTool, slugify

router = APIRouter(tags=["Tasks"])


class TasksFoldersQuery(OPModel):
    filter: Annotated[
        QueryFilter | None,
        Field(title="Filter", description="Filter object used to resolve the tasks"),
    ] = None
    search: Annotated[
        str | None,
        Field(
            title="Text search",
            description="'fulltext' search used to resolve the tasks",
        ),
    ] = None


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
    "active",
    "assignees",
    "attrib",
    "created_at",
    "folder_id",
    "id",
    "label",
    "name",
    "status",
    "tags",
    "task_type",
    "thumbnail_id",
    "updated_at",
]


@router.post("/projects/{project_name}/tasksFolders", deprecated=True)
async def query_tasks_folders(
    user: CurrentUser,
    project_name: ProjectName,
    request: TasksFoldersQuery,
) -> TasksFoldersResponse:
    result = []
    conditions = []

    if request.filter:
        try:
            filter = build_filter(
                request.filter,
                table_prefix="tasks",
                column_whitelist=ALLOWED_KEYS,
                column_map={
                    "attrib": "(coalesce(f.attrib, '{}'::jsonb ) || tasks.attrib)"
                },
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        if filter is not None:
            conditions.append(filter)

    if request.search:
        terms = slugify(request.search, make_set=True)
        # isn't it nice that slugify effectively prevents sql injections?
        for term in terms:
            cond = f"""(
            tasks.name ILIKE '{term}%'
            OR tasks.label ILIKE '{term}%'
            OR tasks.task_type ILIKE '{term}%'
            OR f.path ILIKE '%{term}%'
            )"""
            conditions.append(cond)

    if not conditions:
        raise BadRequestException("No filter or search term provided")

    facl = await folder_access_list(user, project_name, "read")
    if facl is not None:
        cond = f"f.path like ANY ('{{ {','.join(facl)} }}')"
        conditions.append(cond)

    query = f"""
        SELECT DISTINCT tasks.folder_id
        FROM project_{project_name}.tasks tasks
        INNER JOIN project_{project_name}.exported_attributes AS f
        ON tasks.folder_id = f.folder_id
        {SQLTool.conditions(conditions)}
    """

    async for row in Postgres.iterate(query):
        result.append(row["folder_id"])

    return TasksFoldersResponse(folder_ids=result)
