from ayon_server.activities.create_activity import create_activity
from ayon_server.activities.models import ActivityType
from ayon_server.api.dependencies import (
    CurrentUser,
    PathEntityID,
    PathProjectLevelEntityType,
    ProjectName,
)
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .router import router


class ProjectActivityPostModel(OPModel):
    activity_type: ActivityType = Field(..., example="comment")
    body: str = Field("", example="This is a comment")


@router.post("{entity_type}/{entity_id}/activities", status_code=201)
async def post_project_activity(
    project_name: ProjectName,
    entity_type: PathProjectLevelEntityType,
    entity_id: PathEntityID,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
) -> EmptyResponse:
    await create_activity(
        project_name=project_name,
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type=activity.activity_type,
        body=activity.body,
        user_name=user.name,
    )

    return EmptyResponse()
