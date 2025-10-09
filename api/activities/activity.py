from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks

from ayon_server.activities import (
    ActivityType,
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
    Sender,
    SenderType,
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
from ayon_server.types import Field, OPModel

from .router import router


async def delete_unused_files(project_name: str) -> None:
    storage = await Storages.project(project_name)
    await storage.delete_unused_files()


class ProjectActivityPostModel(OPModel):
    id: str | None = Field(None, description="Explicitly set the ID of the activity")
    activity_type: ActivityType = Field(..., example="comment")
    body: str = Field("", example="This is a comment")
    tags: list[str] | None = Field(None, example=["tag1", "tag2"])
    files: list[str] | None = Field(None, example=["file1", "file2"])
    timestamp: datetime | None = Field(None, example="2021-01-01T00:00:00Z")
    data: dict[str, Any] | None = Field(
        None,
        example={"key": "value"},
        description="Additional data",
    )


class CreateActivityResponseModel(OPModel):
    id: str = Field(..., example="123")


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
    sender: Sender,
    sender_type: SenderType,
) -> CreateActivityResponseModel:
    """Create an activity.

    Comment on an entity for example.
    Or subscribe for updates (later)

    """

    if not user.is_service:
        if activity.activity_type not in ["comment"]:
            raise BadRequestException("Humans can only create comments")

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
        user_name=user.name,
        timestamp=activity.timestamp,
        sender=sender,
        sender_type=sender_type,
        data=activity.data,
        bump_entity_updated_at=True,
    )

    if not user.is_service:
        await ensure_watching(entity, user)

    background_tasks.add_task(delete_unused_files, project_name)

    return CreateActivityResponseModel(id=id)


@router.delete("/activities/{activity_id}", dependencies=[AllowGuests])
async def delete_project_activity(
    project_name: ProjectName,
    activity_id: ActivityID,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    sender: Sender,
    sender_type: SenderType,
) -> EmptyResponse:
    """Delete an activity.

    Only the author or an administrator of the activity can delete it.
    """

    await delete_activity(
        project_name,
        activity_id,
        user_name=user.name,
        is_admin=user.is_admin,
        sender=sender,
        sender_type=sender_type,
    )

    background_tasks.add_task(delete_unused_files, project_name)

    return EmptyResponse()


class ActivityPatchModel(OPModel):
    body: str | None = Field(
        None,
        example="This is a comment",
        description="When set, update the activity body",
    )
    tags: list[str] | None = Field(
        None,
        example=["tag1", "tag2"],
        description="When set, update the activity tags",
    )
    files: list[str] | None = Field(
        None,
        example=["file1", "file2"],
        description="When set, update the activity files",
    )
    append_files: bool = Field(
        False,
        example=False,
        description="When true, append files to the existing ones. replace them otherwise",  # noqa: E501
    )
    data: dict[str, Any] | None = Field(None, example={"key": "value"})


@router.patch("/activities/{activity_id}", dependencies=[AllowGuests])
async def patch_project_activity(
    project_name: ProjectName,
    activity_id: ActivityID,
    user: CurrentUser,
    activity: ActivityPatchModel,
    background_tasks: BackgroundTasks,
    sender: Sender,
    sender_type: SenderType,
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
        sender=sender,
        sender_type=sender_type,
        is_admin=user.is_admin,
    )

    background_tasks.add_task(delete_unused_files, project_name)

    return EmptyResponse()
