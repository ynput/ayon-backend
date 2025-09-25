from ayon_server.api.dependencies import (
    CurrentUser,
    FolderID,
    ProjectName,
    Sender,
    SenderType,
)
from ayon_server.lib.postgres import Postgres

from .router import router


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
