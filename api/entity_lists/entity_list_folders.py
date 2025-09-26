from typing import Annotated

from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils.entity_id import EntityID
from ayon_server.utils.utils import dict_patch

from .router import router

#
# Entity list folder models
#


class EntityListFolderData(OPModel):
    color: Annotated[str | None, Field(description="Hex color code")] = None
    icon: Annotated[str | None, Field(description="Icon name")] = None
    scope: Annotated[list[str] | None, Field(description="Folder scope")] = None


FFolderID = Field(title="Folder ID", **EntityID.META)
FFolderLabel = Field(title="Folder label", min_length=1, max_length=255)
FFolderParentID = Field(title="Parent folder ID", **EntityID.META)
FFolderOwner = Field(title="Owner user name", min_length=1, max_length=255)
FFolderAccess = Field(title="Access control list", default_factory=dict)
FFolderData = Field(
    title="Folder additional data",
    default_factory=lambda: EntityListFolderData(),
)

#
# Get / list item model
#


class EntityListFolderPostModel(OPModel):
    id: Annotated[str | None, FFolderID] = None
    label: Annotated[str, FFolderLabel]
    parent_id: Annotated[str | None, FFolderParentID] = None

    access: Annotated[dict[str, int], FFolderAccess]
    data: Annotated[EntityListFolderData, FFolderData]


class EntityListFolderPatchModel(OPModel):
    label: Annotated[str | None, FFolderLabel] = None
    parent_id: Annotated[str | None, FFolderParentID] = None

    access: Annotated[dict[str, int] | None, FFolderAccess]
    data: Annotated[EntityListFolderData | None, FFolderData]


class EntityListFolderModel(OPModel):
    id: Annotated[str, FFolderID]
    label: Annotated[str, FFolderLabel]
    parent_id: Annotated[str | None, FFolderParentID] = None
    position: Annotated[int, Field(title="Folder position", ge=0)] = 0

    owner: Annotated[str | None, FFolderOwner] = None
    access: Annotated[dict[str, int], FFolderAccess]
    data: Annotated[EntityListFolderData, FFolderData]


class EntityListFoldersResponseModel(OPModel):
    folders: Annotated[list[EntityListFolderModel], Field(default_factory=list)]


@router.get("/entityListFolders")
async def get_entity_list_folders(
    user: CurrentUser,
    project_name: ProjectName,
) -> EntityListFoldersResponseModel:
    result = []
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        query = "SELECT * FROM entity_list_folders ORDER BY parent_id, position, label"
        stmt = await Postgres.prepare(query)
        async for row in stmt.cursor():
            result.append(EntityListFolderModel(**row))
            # TODO: acl

    return EntityListFoldersResponseModel(folders=result)


@router.post("/entityListFolders")
async def create_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListFolderPostModel,
) -> EntityIdResponse:
    if payload.id is None:
        payload.id = EntityID.create()

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        try:
            await Postgres.execute(
                """
                INSERT INTO entity_list_folders
                (id, label, parent_id, owner, access, data)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                payload.id,
                payload.label,
                payload.parent_id,
                user.name,
                payload.access,
                payload.data.dict(exclude_unset=True),
            )
        except Postgres.UniqueViolationError:
            raise ConflictException("Folder with the given ID already exists")
    return EntityIdResponse(id=payload.id)


@router.patch("/entityListFolders/{folder_id}")
async def update_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListFolderPatchModel,
) -> EmptyResponse:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        res = await Postgres.fetchrow(
            "SELECT * FROM entity_list_folders WHERE id = $1",
            folder_id,
        )

        if not res:
            raise NotFoundException("Entity list folder not found")

        if not user.is_manager and res["owner"] != user.name:
            raise ForbiddenException("Only owner or manager can update this folder")

        payload_dict = payload.dict(exclude_unset=True)

        new_payload = {
            "label": payload_dict.get("label", res["label"]),
            "parent_id": payload_dict.get("parent_id", res["parent_id"]),
            "access": payload_dict.get("access", res["access"]),
            "data": dict_patch(res["data"] or {}, payload_dict.pop("data", {}) or {}),
        }

        await Postgres.execute(
            """
            UPDATE entity_list_folders
            SET label = $2,
                parent_id = $3,
                access = $4,
                data = $5
            WHERE id = $1
            """,
            folder_id,
            new_payload["label"],
            new_payload["parent_id"],
            new_payload["access"],
            new_payload["data"],
        )

    return EmptyResponse()


@router.delete("/entityListFolders/{folder_id}")
async def delete_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        res = await Postgres.fetchrow(
            "SELECT owner FROM entity_list_folders WHERE id = $1", folder_id
        )

        if not res:
            raise NotFoundException("Entity list folder not found")

        if not user.is_manager and res["owner"] != user.name:
            raise ForbiddenException("Only owner or manager can delete this folder")

        await Postgres.execute(
            "DELETE FROM entity_list_folders WHERE id = $1",
            folder_id,
        )

    return EmptyResponse()


class EntityListFolderOrderModel(OPModel):
    order: Annotated[
        list[str],
        Field(
            title="Ordered list of folder IDs",
            min_items=1,
        ),
    ]


@router.post("/entityListFolders/order")
async def set_entity_list_folders_order(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
    payload: EntityListFolderOrderModel,
) -> EmptyResponse:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)

        for position, folder_id in enumerate(payload.order):
            await Postgres.execute(
                """
                UPDATE entity_list_folders
                SET position = $2
                WHERE id = $1
                """,
                folder_id,
                position,
            )

    return EmptyResponse()
