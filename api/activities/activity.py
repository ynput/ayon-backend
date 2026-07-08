from typing import Annotated

from fastapi import BackgroundTasks

from ayon_server.activities import (
    ActivityPatchModel,
    ProjectActivityPostModel,
    create_activity,
    delete_activity,
    update_activity,
)
from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.activities.guest_access import get_guest_activity_category
from ayon_server.activities.watchers.set_watchers import ensure_watching
from ayon_server.api.dependencies import (
    ActivityID,
    AllowGuests,
    CurrentUser,
    PathEntityID,
    PathProjectLevelEntityType,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.entities import ProjectEntity
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
)
from ayon_server.files import Storages
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.types import OPModel
from ayon_server.utils.entity_id import EntityID

from .router import router

human_activity_types = ["comment", "version.review"]


async def delete_unused_files(project_name: str) -> None:
    storage = await Storages.project(project_name)
    await storage.delete_unused_files()


class CreateActivityResponseModel(OPModel):
    id: Annotated[
        str,
        EntityID.field(name="activity"),
    ]


@router.post(
    "/{entity_type}/{entity_id}/activities",
    status_code=201,
    dependencies=[AllowGuests],
)
async def post_project_activity(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
    background_tasks: BackgroundTasks,
) -> CreateActivityResponseModel:
    """Create an activity.

    Comment on an entity for example.
    Or subscribe for updates (later)

    """

    if not user.is_service:
        if activity.activity_type not in human_activity_types:
            raise BadRequestException("Humans can only create comments/guest reviews")

    project = await ProjectEntity.load(project_name)

    writable_categories = await ActivityCategories.get_accessible_categories(
        user,
        project=project,
        level=EntityAccessHelper.UPDATE,
    )

    if user.is_guest:
        # Guests are only allowed to comment within an entity list / review session
        # and their comment category is defined by the entity list

        entity_list_id = activity.data.get("entityList") if activity.data else None
        list_guest_category = await get_guest_activity_category(
            user,
            project,
            entity_list_id,
        )
        assert activity.data is not None  # shouldn't happen, already checked above
        activity.data["category"] = list_guest_category

        if list_guest_category not in writable_categories:
            raise ForbiddenException("You cannot use this activity category")

    elif not user.is_manager:
        # Normal users - can comment only with their writable categories
        # or without category (default)

        activity_category = activity.data.get("category") if activity.data else None
        if activity_category and activity_category not in writable_categories:
            raise ForbiddenException("You cannot use this activity category")

    #
    # Load entity and check access
    #

    entity_class = get_entity_class(entity_type)
    entity = await entity_class.load(project_name, entity_id)

    if not user.is_guest:
        # guest access is inferred from the entity list / review session,
        # access, which is checked in get_guest_activity_category(),
        await EntityAccessHelper.ensure_entity_access(
            user,
            entity=entity,
            level=EntityAccessHelper.READ,
        )

    #
    # Create activity
    #

    id = await create_activity(
        entity=entity,
        activity_id=activity.id,
        activity_type=activity.activity_type,
        body=activity.body,
        tags=activity.tags,
        files=activity.files,
        user=user,
        timestamp=activity.timestamp,
        data=activity.data,
        bump_entity_updated_at=True,
    )

    if not (user.is_service or user.is_guest):
        await ensure_watching(entity, user)

    background_tasks.add_task(delete_unused_files, project_name)

    return CreateActivityResponseModel(id=id)


@router.delete("/activities/{activity_id}", dependencies=[AllowGuests])
async def delete_project_activity(
    project_name: ProjectName,
    activity_id: ActivityID,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EmptyResponse:
    """Delete an activity.

    Only the author or an administrator of the activity can delete it.
    """

    await delete_activity(
        project_name,
        activity_id,
        user_name=user.name,
        is_admin=user.is_admin,
    )

    background_tasks.add_task(delete_unused_files, project_name)

    return EmptyResponse()


@router.patch("/activities/{activity_id}", dependencies=[AllowGuests])
async def patch_project_activity(
    project_name: ProjectName,
    activity_id: ActivityID,
    user: CurrentUser,
    activity: ActivityPatchModel,
    background_tasks: BackgroundTasks,
) -> EmptyResponse:
    """Edit an activity.

    Administrators can edit any activity.
    Users with the access to the project can edit their own activities,
    and tick/untick checkboxes in the comment
    """

    await user.ensure_project_access(project_name)

    user_name = user.name

    await update_activity(
        project_name=project_name,
        activity_id=activity_id,
        body=activity.body,
        tags=activity.tags,
        files=activity.files,
        append_files=activity.append_files,
        data=activity.data,
        user_name=user_name,
        is_admin=user.is_admin,
    )

    background_tasks.add_task(delete_unused_files, project_name)

    return EmptyResponse()
