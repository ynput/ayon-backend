from ayon_server.activities.models import (
    ActivityTopic,
    EntityReferenceModel,
    UserReferenceModel,
)
from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .router import router


async def ensure_project_activity_table_exists():
    pass


class ProjectActivityPostModel(OPModel):
    topic: ActivityTopic = Field(ActivityTopic.comment, example="comment")
    body: str = Field("", example="This is a comment")
    entity_references: list[EntityReferenceModel] = Field(default_factory=list)
    user_references: list[UserReferenceModel] = Field(default_factory=list)


@router.post("", status_code=201)
async def post_project_activity(
    project_name: ProjectName,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
) -> EmptyResponse:
    pass
