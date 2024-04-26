import datetime
from typing import Any, Literal

from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

ActivityType = Literal[
    "comment",
    "status.change",
    "assignee.add",
    "assignee.remove",
    "version.publish",
]

ActivityReferenceType = Literal[
    "origin",
    "mention",
    "author",
    "relation",
]

ReferencedEntityType = Literal[
    "activity",
    "user",
    "folder",
    "task",
    "product",
    "version",
    "representation",
    "workfile",
]

EntityLinkTuple = tuple[ReferencedEntityType, str]


class ActivityReferenceModel(OPModel):
    id: str = Field(default_factory=create_uuid)
    reference_type: ActivityReferenceType = Field(..., example="mention")
    entity_type: ReferencedEntityType = Field(..., example="task")
    entity_id: str | None = Field(None, example="1234567890")
    entity_name: str | None = Field(None, example="admin")

    data: dict[str, Any] = Field(default_factory=dict)

    # TODO: validate whether the entity_id is present when the entity_type is not user
    # TODO: validate whether the entity_name is present when the entity_type is user

    def insertable_tuple(
        self,
        activity_id: str,
        timestamp: datetime.datetime | None = None,
    ) -> tuple:
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)
        return (
            self.id,
            activity_id,
            self.reference_type,
            self.entity_type,
            self.entity_id,
            self.entity_name,
            self.data,
            timestamp,
        )

    def __hash__(self):
        return (
            self.reference_type,
            self.entity_type,
            self.entity_id,
            self.entity_name,
        )
