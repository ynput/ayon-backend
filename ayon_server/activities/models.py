from typing import Literal

from ayon_server.types import Field, OPModel

EntityLinkTuple = tuple[str, str]

ActivityType = Literal["comment"]
EntityReferenceType = Literal["origin", "mention"]
UserReferenceType = Literal["author", "mention", "watcher"]


class EntityReferenceModel(OPModel):
    entity_id: str = Field(..., example="1234567890")
    entity_type: str = Field(..., example="task")
    reference_type: EntityReferenceType = Field(..., example="mention")
    data: dict[str, str] = Field(default_factory=dict)


class UserReferenceModel(OPModel):
    user_name: str = Field(..., example="user1")
    reference_type: UserReferenceType = Field(..., example="mention")
    data: dict[str, str] = Field(default_factory=dict)
