from datetime import datetime

from fastapi import BackgroundTasks

from ayon_server.activities import (
    ActivityType,
    create_activity,
    delete_activity,
    update_activity,
)
from ayon_server.api.dependencies import (
    CurrentUser,
    PathEntityID,
    PathProjectLevelEntityType,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.helpers.project_files import delete_unused_files
from ayon_server.types import Field, OPModel

from .router import router


class ProjectActivityPostModel(OPModel):
    id: str | None = Field(None, description="Explicitly set the ID of the activity")
    activity_type: ActivityType = Field(..., example="comment")
    body: str = Field("", example="This is a comment")
    files: list[str] | None = Field(None, example=["file1", "file2"])
    timestamp: datetime | None = Field(None, example="2021-01-01T00:00:00Z")


class CreateActivityResponseModel(OPModel):
    id: str = Field(..., example="123")


@router.post("/{entity_type}/{entity_id}/activities", status_code=201)
async def post_project_activity(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
) -> CreateActivityResponseModel:
    """Create an activity.

    Comment on an entity for example.
    Or subscribe for updates (later)

    """

    if not user.is_service:
        if activity.activity_type != "comment":
            raise BadRequestException("Humans can only create comments")

    entity_class = get_entity_class(entity_type)
    entity = await entity_class.load(project_name, entity_id)

    # TODO: remove before merge
    # await entity.ensure_read_access(user)  # TODO: different acl level?

    id = await create_activity(
        entity=entity,
        activity_id=activity.id,
        activity_type=activity.activity_type,
        body=activity.body,
        files=activity.files,
        user_name=user.name,
        timestamp=activity.timestamp,
    )

    return CreateActivityResponseModel(id=id)


@router.delete("/activities/{activity_id}")
async def delete_project_activity(
    project_name: ProjectName,
    activity_id: str,
    user: CurrentUser,
) -> EmptyResponse:
    """Delete an activity.

    Only the author or an administrator of the activity can delete it.
    """

    if user.is_admin:
        # admin can delete any activity
        user_name = None
    else:
        user_name = user.name

    await delete_activity(project_name, activity_id, user_name=user_name)

    return EmptyResponse()


class ActivityPatchModel(OPModel):
    body: str = Field(..., example="This is a comment")
    files: list[str] | None = Field(None, example=["file1", "file2"])


@router.patch("/activities/{activity_id}")
async def patch_project_activity(
    project_name: ProjectName,
    activity_id: str,
    user: CurrentUser,
    activity: ActivityPatchModel,
    background_tasks: BackgroundTasks,
) -> EmptyResponse:
    """Edit an activity.

    Only the author of the activity can edit it.
    """

    if user.is_admin:
        # admin can delete any activity
        user_name = None
    else:
        user_name = user.name

    await update_activity(
        project_name=project_name,
        activity_id=activity_id,
        body=activity.body,
        files=activity.files,
        user_name=user_name,
    )

    background_tasks.add_task(delete_unused_files, project_name)

    return EmptyResponse()
