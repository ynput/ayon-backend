from typing import Annotated

from ayon_server.access.utils import folder_access_list
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.sqlfilter import QueryFilter, build_filter
from ayon_server.types import Field, OPModel
from ayon_server.utils import SQLTool, slugify

from .router import router


class FolderSearchRequest(OPModel):
    task_filter: Annotated[
        QueryFilter | None,
        Field(title="Filter", description="Filter object used to resolve the tasks"),
    ] = None

    task_search: Annotated[
        str | None,
        Field(
            title="Text search",
            description="'fulltext' search used to resolve the tasks",
        ),
    ] = None

    folder_filter: Annotated[
        QueryFilter | None,
        Field(
            title="Folder Filter",
            description="Filter object used to resolve the folders",
        ),
    ] = None

    folder_search: Annotated[
        str | None,
        Field(
            title="Folder Text search",
            description="'fulltext' search used to resolve the folders",
        ),
    ] = None


class FolderSearchResponse(OPModel):
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


TASK_ALLOWED_KEYS = [
    "id",
    "name",
    "label",
    "task_type",
    "assignees",
    "status",
    "attrib",
    "data",
    "tags",
    "active",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
]


FOLDER_ALLOWED_FIELDS = [
    "id",
    "name",
    "label",
    "folder_type",
    "parent_id",
    "attrib",
    "data",
    "active",
    "status",
    "tags",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
]


@router.post("/search")
async def search_folders(
    user: CurrentUser,
    project_name: ProjectName,
    payload: FolderSearchRequest,
) -> FolderSearchResponse:
    sql_cte = []
    sql_joins = []
    sql_conditions = []

    #
    # Filtering by tasks
    #

    if payload.task_filter or payload.task_search:
        task_conditions = []

        if payload.task_filter:
            if tcond := build_filter(
                payload.task_filter,
                table_prefix="tasks",
                column_whitelist=TASK_ALLOWED_KEYS,
                column_map={"attrib": "(ex.attrib || tasks.attrib)"},
            ):
                task_conditions.append(tcond)

        if payload.task_search:
            terms = slugify(payload.task_search, make_set=True)
            for term in terms:
                cond = f"""(
                tasks.name ILIKE '{term}%'
                OR tasks.label ILIKE '{term}%'
                OR tasks.task_type ILIKE '{term}%'
                OR ex.path ILIKE '%{term}%'
                )"""
                task_conditions.append(cond)

        sql_cte.append(
            f"""
            filtered_tasks AS (
                SELECT DISTINCT tasks.folder_id
                FROM project_{project_name}.tasks AS tasks
                JOIN project_{project_name}.exported_attributes as ex
                ON tasks.folder_id = ex.folder_id
                {SQLTool.conditions(task_conditions)}
            )
            """
        )

        sql_joins.append(
            """
            JOIN filtered_tasks AS ft
            ON ft.folder_id = folders.id
            """
        )

    #
    # Filtering by folders
    #

    if payload.folder_filter:
        if fcond := build_filter(
            payload.folder_filter,
            column_whitelist=FOLDER_ALLOWED_FIELDS,
            table_prefix="folders",
            column_map={
                "attrib": "e.attrib",
                "path": "e.path",
            },
        ):
            sql_conditions.append(fcond)

    if payload.folder_search:
        terms = slugify(payload.folder_search, make_set=True)
        for term in terms:
            sql_conditions.append(
                f"(folders.name ILIKE '%{term}%' OR "
                f"folders.label ILIKE '%{term}%' OR "
                f"e.path ILIKE '%{term}%')"
            )

    facl = await folder_access_list(user, project_name, "read")
    if facl is not None:
        cond = f"e.path like ANY ('{{ {','.join(facl)} }}')"
        sql_conditions.append(cond)

    #
    # Query
    #

    if sql_cte:
        cte = ", ".join(sql_cte)
        cte = f"WITH {cte}"
    else:
        cte = ""

    query = f"""
        {cte}
        SELECT folders.id AS folder_id
        FROM project_{project_name}.folders AS folders
        JOIN project_{project_name}.exported_attributes AS e
        ON folders.id = e.folder_id
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
    """
    result = []
    async for row in Postgres.iterate(query):
        result.append(row["folder_id"])

    return FolderSearchResponse(folder_ids=result)
