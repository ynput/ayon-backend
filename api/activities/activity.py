from ayon_server.activities.create_activity import create_activity
from ayon_server.activities.models import (
    ActivityType,
    EntityReferenceModel,
    UserReferenceModel,
)
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .router import router


class ProjectActivityPostModel(OPModel):
    type: ActivityType = Field(ActivityType.comment, example="comment")
    body: str = Field("", example="This is a comment")
    entity_references: list[EntityReferenceModel] = Field(default_factory=list)
    user_references: list[UserReferenceModel] = Field(default_factory=list)


@router.post("", status_code=201)
async def post_project_activity(
    project_name: ProjectName,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
) -> EmptyResponse:
    await create_activity(
        project_name=project_name,
        activity_type=activity.type,
        body=activity.body,
        entity_references=activity.entity_references,
        user_references=activity.user_references,
        user=user.name,
    )

    return EmptyResponse()
