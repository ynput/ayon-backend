from enum import Enum

from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.api.responses import EmptyResponse
from ayon_server.types import Field, OPModel

from .router import router


async def ensure_project_activity_table_exists():
    pass


class ActivityTopic(str, Enum):
    comment = "comment"


class ReferenceType(str, Enum):
    origin = "origin"  # comment was created on this entity
    mention = "mention"  # entity was mentioned in this comment


class EntityReferenceModel(OPModel):
    entity_id: str = Field(..., example="1234567890")
    entity_type: str = Field(..., example="task")
    reference_type: ReferenceType = Field(..., example="mention")


class ProjectActivityPostModel(OPModel):
    topic: ActivityTopic = Field(ActivityTopic.comment, example="comment")
    description: str = Field("", example="This is a comment")
    entity_references: list[EntityReferenceModel] = Field(default_factory=list)


@router.post("", status_code=201)
async def post_project_activity(
    project_name: ProjectName,
    user: CurrentUser,
    activity: ProjectActivityPostModel,
) -> EmptyResponse:
    referenced_users = set()

    referenced_users.add(user.name)
