from typing import Annotated

from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import Field, OPModel
from ayon_server.utils.entity_id import EntityID
from ayon_server.utils.utils import dict_patch

from .router import router

#
# Project folder models
#


class ProjectFolderData(OPModel):
    color: Annotated[str | None, Field(description="Hex color code")] = None
    icon: Annotated[str | None, Field(description="Icon name")] = None


FFolderID = Field(title="Folder ID", **EntityID.META)
FFolderLabel = Field(title="Folder label", min_length=1, max_length=255)
FFolderParentID = Field(title="Parent folder ID", **EntityID.META)
FFolderData = Field(
    title="Folder additional data",
    default_factory=lambda: ProjectFolderData(),
)

#
# Get / list item model
#


class ProjectFolderPostModel(OPModel):
    id: Annotated[str | None, FFolderID] = None
    label: Annotated[str, FFolderLabel]
    parent_id: Annotated[str | None, FFolderParentID] = None
    data: Annotated[ProjectFolderData, FFolderData]


class ProjectFolderPatchModel(OPModel):
    label: Annotated[str | None, FFolderLabel] = None
    parent_id: Annotated[str | None, FFolderParentID] = None
    data: Annotated[ProjectFolderData | None, FFolderData]


class ProjectFolderModel(OPModel):
    id: Annotated[str, FFolderID]
    label: Annotated[str, FFolderLabel]
    parent_id: Annotated[str | None, FFolderParentID] = None
    position: Annotated[int, Field(title="Folder position", ge=0)] = 0
    data: Annotated[ProjectFolderData, FFolderData]


class ProjectFoldersResponseModel(OPModel):
    folders: Annotated[list[ProjectFolderModel], Field(default_factory=list)]


#
# API endpoints
#


@router.get("/projectFolders")
async def get_project_folders(user: CurrentUser) -> ProjectFoldersResponseModel:
    result = []
    async with Postgres.transaction():
        query = "SELECT * FROM project_folders ORDER BY parent_id, position, label"
        stmt = await Postgres.prepare(query)
        async for row in stmt.cursor():
            result.append(ProjectFolderModel(**row))

    return ProjectFoldersResponseModel(folders=result)


@router.post("/projectFolders")
async def create_project_folder(
    user: CurrentUser,
    payload: ProjectFolderPostModel,
) -> EntityIdResponse:
    if payload.id is None:
        payload.id = EntityID.create()

    try:
        await Postgres.execute(
            """
            INSERT INTO project_folders
            (id, label, parent_id, data)
            VALUES ($1, $2, $3, $4)
            """,
            payload.id,
            payload.label,
            payload.parent_id,
            payload.data.dict(exclude_unset=True),
        )
    except Postgres.UniqueViolationError:
        raise ConflictException("Folder with the given ID already exists")
    return EntityIdResponse(id=payload.id)


@router.patch("/projectFolders/{folder_id}")
async def update_project_folder(
    user: CurrentUser,
    folder_id: FolderID,
    payload: ProjectFolderPatchModel,
) -> EmptyResponse:
    async with Postgres.transaction():
        res = await Postgres.fetchrow(
            "SELECT * FROM project_folders WHERE id = $1",
            folder_id,
        )

        if not res:
            raise NotFoundException("Project folder not found")

        if not user.is_admin:
            raise ForbiddenException("You don't have permission to update this folder")

        payload_dict = payload.dict(exclude_unset=True)

        new_payload = {
            "label": payload_dict.get("label", res["label"]),
            "parent_id": payload_dict.get("parent_id", res["parent_id"]),
            "data": dict_patch(res["data"] or {}, payload_dict.pop("data", {}) or {}),
        }

        await Postgres.execute(
            """
            UPDATE project_folders
            SET label = $2,
                parent_id = $3,
                data = $4
            WHERE id = $1
            """,
            folder_id,
            new_payload["label"],
            new_payload["parent_id"],
            new_payload["data"],
        )

    return EmptyResponse()


@router.delete("/projectFolders/{folder_id}")
async def delete_project_folder(
    user: CurrentUser,
    folder_id: FolderID,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("You don't have permission to delete project folders")
    await Postgres.execute(
        "DELETE FROM project_folders WHERE id = $1",
        folder_id,
    )
    return EmptyResponse()


class ProjectFolderOrderModel(OPModel):
    order: Annotated[
        list[str],
        Field(
            title="Ordered list of folder IDs",
            min_items=1,
        ),
    ]


@router.post("/projectFolders/order")
async def set_project_folders_order(
    user: CurrentUser,
    payload: ProjectFolderOrderModel,
) -> EmptyResponse:
    if not user.is_admin:
        raise ForbiddenException("You don't have permission to reorder project folders")

    async with Postgres.transaction():
        for position, folder_id in enumerate(payload.order):
            await Postgres.execute(
                """
                UPDATE project_folders
                SET position = $2
                WHERE id = $1
                """,
                folder_id,
                position,
            )

    return EmptyResponse()


class AssignProjectRequest(OPModel):
    folder_id: Annotated[str | None, FFolderID] = None
    project_names: Annotated[
        list[str],
        Field(
            title="List of project names to assign to the folder",
            min_items=1,
        ),
    ]


@router.post("/projectFolders/assign")
async def assign_projects_to_folder(
    user: CurrentUser,
    payload: AssignProjectRequest,
) -> EmptyResponse:
    """Assign one or more projects to a project folder.

    To remove projects from folders, set `folder_id` to `null`.
    Only users with manager privileges can perform this action.
    """
    if not user.is_manager:
        raise ForbiddenException(
            "You don't have permission to assign projects to folders"
        )

    for project_name_input in payload.project_names:
        project_name = await normalize_project_name(project_name_input)

        folder_id = EntityID.parse(payload.folder_id, allow_nulls=True)

        if folder_id is None:
            await Postgres.execute(
                """
                UPDATE projects
                SET data = data - 'projectFolder'
                WHERE name = $1
                """,
                project_name,
            )
        else:
            await Postgres.execute(
                """
                UPDATE projects
                SET data = jsonb_set(
                    COALESCE(data, '{}'::jsonb),
                    '{projectFolder}',
                    to_jsonb($2::text)
                )
                WHERE name = $1
                """,
                project_name,
                folder_id,
            )
        await Redis.delete("project-data", project_name)

    return EmptyResponse()
