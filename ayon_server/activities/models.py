from enum import Enum

from ayon_server.types import Field, OPModel


class ActivityType(str, Enum):
    comment = "comment"


class EntityReferenceType(str, Enum):
    origin = "origin"  # activity was created on this entity
    mention = "mention"  # entity was mentioned in the activity


class EntityReferenceModel(OPModel):
    entity_id: str = Field(..., example="1234567890")
    entity_type: str = Field(..., example="task")
    reference_type: EntityReferenceType = Field(..., example="mention")


class UserReferenceModel(OPModel):
    user_name: str = Field(..., example="user1")
    roles: list[str] = Field(default_factory=list, example=["author", "mention"])
