from datetime import datetime
from typing import TYPE_CHECKING, ForwardRef, Literal

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router


class SuggestRequest(OPModel):
    entity_type: Literal["folder", "task", "version"] = Field(..., example="task")
    entity_id: str = Field(..., example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b")


if not TYPE_CHECKING:
    SuggestionItem = ForwardRef("SuggestionItem")


class SuggestionItem(OPModel):
    type: Literal["task", "version", "user"] = Field(
        ...,
        example="task",
        title="Entity type",
    )
    id: str | None = Field(
        None,
        type="Entity ID",
        description="For versions and tasks",
        example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
    )
    subtype: str | None = Field(
        None,
        example="Modeling",
        description="Task type for tasks",
    )
    name: str | None = Field(
        None,
        example="Task 1",
        description="Name of the entity (for tasks and users)",
    )
    label: str | None = Field(
        None,
        example="Task 1",
        description="Label of the entity (for tasks)",
    )
    version: int | None = Field(
        None,
        example=1,
        description="Version of the entity (for versions)",
    )
    thumbnail_id: str | None = Field(
        None,
        example="af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
    )
    created_at: datetime = Field()
    parent: SuggestionItem | None = Field(None, description="Parent entity")


SuggestionItem.update_forward_refs()


class SuggestResponse(OPModel):
    suggestions: list[SuggestionItem] = Field(
        default_factory=list,
        description="List of suggested mentions for the entity",
        example=[
            {
                "id": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                "type": "task",
                "subtype": "Modeling",
                "name": "modeling",
                "label": None,
                "thumbnailId": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                "createdAt": "2021-09-01T00:00:00Z",
                "parent": {
                    "id": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                    "type": "folder",
                    "name": "my_character",
                    "label": "My Character",
                },
            },
            {
                "id": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                "type": "version",
                "version": 1,
                "thumbnailId": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                "createdAt": "2021-09-01T00:00:00Z",
                "parent": {
                    "id": "af3e4b3e-1b1b-4b3b-8b3b-3b3b3b3b3b3b",
                    "type": "product",
                    "subtype": "model",
                    "name": "model_main",
                },
            },
        ],
    )


#
# Resolving
#


async def get_folder_suggestions(
    project_name: str, folder_id: str
) -> list[SuggestionItem]:
    """
    Assignees: Every assignee in the project
    Versions: Disabled - what versions would you want to see on a folder?
    Tasks: Direct child tasks of the folder.
    """

    folder_data_res = await Postgres.fetch(
        f"""
        SELECT h.path as path
        FROM project_{project_name}.hierarchy h
        WHERE h.id = $1
        """
    )
    if not folder_data_res:
        return []

    folder_data = folder_data_res[0]
    folder_path = folder_data["path"]

    result = []

    # get users:

    query = f"""
        SELECT
            u.name as name,
            u.attrib->>'fullName' as label,
            r.rel_count as has_task
        FROM users u,
        LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.tasks t
            JOIN project_{project_name}.hierarchy h ON t.folder_id = h.id
            WHERE t.assignees @> ARRAY[u.name]
            AND h.path LIKE '{folder_path}%'
        ) r ORDER BY r.rel_count DESC;
    """

    async for row in Postgres.iterate(query):
        result.append(SuggestionItem(type="user", name=row["name"], label=row["label"]))

    # Get tasks

    query = f"""
    SELECT
        t.id as task_id,
        t.task_type as task_type,
        t.name as task_name,
        t.label as task_label,
        t.thumbnail_id as task_thumbnail_id,
        t.created_at as task_created_at,
        f.id as folder_id,
        f.name as folder_name,
        f.label as folder_label
        f.folder_type as folder_type,
        f.thumbnail_id as folder_thumbnail_id,
        f.created_at as folder_created_at
    FROM project_{project_name}.tasks t
    JOIN project_{project_name}.folders f ON t.folder_id = f.id
    ORDER BY t.name ASC;

    """

    async for row in Postgres.iterate(query):
        parent = SuggestionItem(
            id=row["folder_id"],
            type="folder",
            subtype=row["folder_type"],
            name=row["folder_name"],
            label=row["folder_label"],
            thumbnail_id=row["folder_thumbnail_id"],
            created_at=row["folder_created_at"],
        )
        result.append(
            SuggestionItem(
                id=row["task_id"],
                type="task",
                subtype=row["task_type"],
                name=row["task_name"],
                label=row["task_label"],
                thumbnail_id=row["task_thumbnail_id"],
                created_at=row["task_created_at"],
                parent=parent,
            )
        )

    return result


async def get_task_suggestions(project_name: str, task_id: str) -> list[SuggestionItem]:
    """
    Assignees: Every assignee in the project, sorted by assignees first.
    Versions: Every version linked to the task.
    Tasks: Direct sibling tasks to the task.
    """
    result = []

    return result


async def get_version_suggestions(
    project_name: str,
    version_id: str,
) -> list[SuggestionItem]:
    """
    Assignees: Every assignee in the project, sorted by author first.
    Versions: Direct sibling versions to the version.
    Tasks: Direct sibling tasks to the parent task of the version.
    """

    result = []

    product_result = await Postgres.fetch(
        f"""
        SELECT
            p.id as product_id
            p.name as product_name,
            p.product_type as product_type
        FROM project_{project_name}.products p
        JOIN project_{project_name}.versions v ON p.id = v.product_id
        WHERE v.id = $1;
    """,
        version_id,
    )

    if not product_result:
        return []

    product = product_result[0]

    # get users:

    query = f"""
        SELECT
            u.name as name,
            u.attrib->>'fullName' as label,
            vref.rel_count as relevance,
        FROM users u
        LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.versions v
            WHERE v.author = u.name
            AND v.id = $1
        ) vref,
        LATERAL (
            SELECT count(*) as rel_count
            FROM project_{project_name}.versions v
            WHERE v.assignees @> ARRAY[u.name]
            AND v.product_id = $2
        ) as pref

        ORDER BY vref.rel_count, pref.rel_count DESC;
    """

    async for row in Postgres.iterate(query, version_id, product["product_id"]):
        result.append(SuggestionItem(type="user", name=row["name"], label=row["label"]))

    # Get versions

    return result


#
# Routing
#


@router.post("/suggest")
async def suggest_entity_mention(
    user: CurrentUser,
    project_name: ProjectName,
    request: SuggestRequest,
) -> SuggestResponse:
    if request.entity_type == "folder":
        res = await get_folder_suggestions(project_name, request.entity_id)
    elif request.entity_type == "task":
        res = await get_task_suggestions(project_name, request.entity_id)
    elif request.entity_type == "version":
        res = await get_version_suggestions(project_name, request.entity_id)
    else:
        res = []

    return SuggestResponse(suggestions=res)
