from fastapi import APIRouter, BackgroundTasks, Depends, Header, Response
from nxtools import logging

from ayon_server.api.dependencies import (
    dep_current_user,
    dep_project_name,
    dep_subset_id,
)
from ayon_server.api.responses import EntityIdResponse, ResponseFactory
from ayon_server.entities import SubsetEntity, UserEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

router = APIRouter(
    tags=["Subsets"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)

#
# [GET]
#


@router.get(
    "/projects/{project_name}/subsets/{subset_id}",
    response_model=SubsetEntity.model.main_model,
    response_model_exclude_none=True,
    responses={404: ResponseFactory.error(404, "Subset not found")},
)
async def get_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
):
    """Retrieve a subset by its ID."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.ensure_read_access(user)
    return subset.as_user(user)


#
# [POST]
#


@router.post(
    "/projects/{project_name}/subsets",
    status_code=201,
    response_model=EntityIdResponse,
    responses={
        409: ResponseFactory.error(409, "Coflict"),
    },
)
async def create_subset(
    post_data: SubsetEntity.model.post_model,  # type: ignore
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
):
    """Create a new subset."""

    subset = SubsetEntity(project_name=project_name, payload=post_data.dict())
    await subset.ensure_create_access(user)
    await subset.save()
    logging.info(f"[POST] Created subset {subset.name}", user=user.name)
    return EntityIdResponse(id=subset.id)


#
# [PATCH]
#


@router.patch(
    "/projects/{project_name}/subsets/{subset_id}",
    status_code=204,
    response_class=Response,
)
async def update_subset(
    post_data: SubsetEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
    x_sender: str | None = Header(default=None),
):
    """Patch (partially update) a subset."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.ensure_update_access(user)
    events = build_pl_entity_change_events(subset, post_data)
    subset.patch(post_data)
    await subset.save()
    for event in events:
        background_tasks.add_task(
            dispatch_event,
            sender=x_sender,
            user=user.name,
            **event,
        )
    return Response(status_code=204)


#
# [DELETE]
#


@router.delete(
    "/projects/{project_name}/subsets/{subset_id}",
    response_class=Response,
    status_code=204,
)
async def delete_subset(
    user: UserEntity = Depends(dep_current_user),
    project_name: str = Depends(dep_project_name),
    subset_id: str = Depends(dep_subset_id),
):
    """Delete a subset."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.ensure_delete_access(user)
    await subset.delete()
    logging.info(f"[DELETE] Deleted subset {subset.name}", user=user.name)
    return Response(status_code=204)
