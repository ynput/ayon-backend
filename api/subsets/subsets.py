from fastapi import APIRouter, BackgroundTasks, Header

from ayon_server.api.dependencies import CurrentUser, ProjectName, SubsetID
from ayon_server.api.responses import EmptyResponse, EntityIdResponse
from ayon_server.entities import SubsetEntity
from ayon_server.events import dispatch_event
from ayon_server.events.patch import build_pl_entity_change_events

router = APIRouter(tags=["Subsets"])

#
# [GET]
#


@router.get(
    "/projects/{project_name}/subsets/{subset_id}", response_model_exclude_none=True
)
async def get_subset(
    user: CurrentUser,
    project_name: ProjectName,
    subset_id: SubsetID,
) -> SubsetEntity.model.main_model:  # type: ignore
    """Retrieve a subset by its ID."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.ensure_read_access(user)
    return subset.as_user(user)


#
# [POST]
#


@router.post("/projects/{project_name}/subsets", status_code=201)
async def create_subset(
    post_data: SubsetEntity.model.post_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    x_sender: str | None = Header(default=None),
) -> EntityIdResponse:
    """Create a new subset."""

    subset = SubsetEntity(project_name=project_name, payload=post_data.dict())
    await subset.ensure_create_access(user)
    event = {
        "topic": "entity.subset.created",
        "description": f"Subset {subset.name} created",
        "summary": {"entityId": subset.id, "parentId": subset.parent_id},
        "project": project_name,
    }
    await subset.save()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EntityIdResponse(id=subset.id)


#
# [PATCH]
#


@router.patch("/projects/{project_name}/subsets/{subset_id}", status_code=204)
async def update_subset(
    post_data: SubsetEntity.model.patch_model,  # type: ignore
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    subset_id: SubsetID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
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
    return EmptyResponse(status_code=204)


#
# [DELETE]
#


@router.delete("/projects/{project_name}/subsets/{subset_id}")
async def delete_subset(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_name: ProjectName,
    subset_id: SubsetID,
    x_sender: str | None = Header(default=None),
) -> EmptyResponse:
    """Delete a subset."""

    subset = await SubsetEntity.load(project_name, subset_id)
    await subset.ensure_delete_access(user)
    event = {
        "topic": "entity.subset.deleted",
        "description": f"Subset {subset.name} deleted",
        "summary": {"entityId": subset.id, "parentId": subset.parent_id},
        "project": project_name,
    }
    await subset.delete()
    background_tasks.add_task(
        dispatch_event,
        sender=x_sender,
        user=user.name,
        **event,
    )
    return EmptyResponse()
