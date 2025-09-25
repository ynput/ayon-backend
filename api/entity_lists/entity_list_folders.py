from typing import Annotated

from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel
from ayon_server.utils.entity_id import EntityID

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

    owner: Annotated[str | None, FFolderOwner] = None
    access: Annotated[dict[str, int], FFolderAccess]
    data: Annotated[EntityListFolderData, FFolderData]


class EntityListFolderPatchModel(OPModel):
    label: Annotated[str | None, FFolderLabel] = None
    parent_id: Annotated[str | None, FFolderParentID] = None

    owner: Annotated[str | None, FFolderOwner] = None
    access: Annotated[dict[str, int] | None, FFolderAccess]
    data: Annotated[EntityListFolderData | None, FFolderData]


class EntityListModel(OPModel):
    id: Annotated[str, FFolderID]
    label: Annotated[str, FFolderLabel]
    parent_id: Annotated[str | None, FFolderParentID] = None

    owner: Annotated[str | None, FFolderOwner] = None
    access: Annotated[dict[str, int], FFolderAccess]
    data: Annotated[EntityListFolderData, FFolderData]

    path: Annotated[
        list[str],
        Field(
            description="List of folder labels from root to this folder",
            default_factory=list,
        ),
    ]

    parents: Annotated[
        list[str],
        Field(
            description="List of parent folder IDs",
            default_factory=list,
        ),
    ]


@router.get("/entityListFolders")
async def get_entity_list_folders(
    user: CurrentUser,
    project_name: ProjectName,
):
    pass


@router.post("/entityListFolders")
async def create_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    sender: Sender,
    sender_type: SenderType,
):
    pass


@router.patch("/entityListFolders/{folder_id}")
async def update_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
) -> None:
    pass


@router.delete("/entityListFolders/{folder_id}")
async def delete_entity_list_folder(
    user: CurrentUser,
    project_name: ProjectName,
    folder_id: FolderID,
    sender: Sender,
    sender_type: SenderType,
) -> None:
    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        await Postgres.execute(
            "DELETE FROM entity_list_folders WHERE id = $1",
            folder_id,
        )
