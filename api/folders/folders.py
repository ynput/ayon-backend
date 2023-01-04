from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response
from nxtools import logging

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_folder_id,
    dep_project_name,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import FolderEntity, UserEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres

router = APIRouter(
    tags=["Folders"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/folders/{folder_id}",
    response_model=FolderEntity.model.main_model,
    response_model_exclude_none=True,
    responses={
        404: ResponseFactory.error(404, "Project not found"),
    },
)
async def get_folder(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Retrieve a folder by its ID."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_read_access(user)
    return folder.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/folders",
    status_code=201,
    response_model=EntityIdResponse,
)
async def create_folder(
    post_data: FolderEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new folder."""

    folder = FolderEntity(project_name=project_name, payload=post_data.dict())
    await folder.ensure_create_access(user)
    await folder.save()
    logging.info(f"[POST] Created folder {folder.name}", user=user.name)
    return EntityIdResponse(id=folder.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/folders/{folder_id}",
    status_code=204,
    response_class=Response,
)
async def update_folder(
    post_data: FolderEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
    x_sender: str | None = Header(default=None),
):
    """Patch (partially update) a folder.

    Once there is a version published, the folder's name and hierarchy
    cannot be changed.
    """

    async with Postgres.acquire() as conn:
        async with conn.transaction():
            folder = await FolderEntity.load(
                project_name, folder_id, transaction=conn, for_update=True
            )

            await folder.ensure_update_access(user)
            has_versions = not not (await folder.get_versions(conn))

            # If the folder has versions, we can't update the name,
            # folder_type or change the hierarchy
            for key in ["name", "folder_type", "parent_id"]:
                old_value = folder.payload.dict(exclude_none=True).get(key)
                new_value = post_data.dict(exclude_none=None).get(key)

                if (new_value is None) or (old_value == new_value):
                    continue

                if has_versions:
                    raise ForbiddenException(
                        f"Cannot update {key} folder with published versions"
                    )

            events = build_pl_entity_change_events(
                folder,
                post_data,
                user,
                x_sender,
            )

            folder.patch(post_data)
            await folder.save(transaction=conn)
            await folder.commit(conn)

            for event in events:
                background_tasks.add_task(
                    dispatch_event,
                    sender=x_sender,
                    user=user.name,
                    **event,
                )

            # background_tasks.add_task(
            #     dispatch_event,
            #     "entity.update",
            #     sender=x_sender,
            #     project=project_name,
            #     user=user.name,
            #     description=f"Updated {folder.path}",
            #     summary={
            #         "entityType": "folder",
            #         "ids": [folder.id],
            #         "parents": [folder.parent_id],
            #     },
            # )

    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/folders/{folder_id}",
    response_class=Response,
    status_code=204,
)
async def delete_folder(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    folder_id: str = Depends(dep_folder_id),
):
    """Delete a folder."""

    folder = await FolderEntity.load(project_name, folder_id)
    await folder.ensure_delete_access(user)
    await folder.delete()
    logging.info(f"[DELETE] Deleted folder {folder.name}", user=user.name)
    return Response(status_code=204)
