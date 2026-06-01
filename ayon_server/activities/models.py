import datetime
from typing import Any, Literal

from ayon_server.types import Field, OPModel
from ayon_server.utils import create_uuid

ActivityType = Literal[
    "comment",
    "watch",
    "reviewable",
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
    "watching",
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
    "team",
]

EntityLinkTuple = tuple[ReferencedEntityType, str]

# For the following activities activity.* events are not created
# since they already originate from events. We only send the event
# over websocket, but do not store them in the database.

DO_NOT_TRACK_ACTIVITIES: set[ActivityType] = {
    "status.change",
    "assignee.add",
    "assignee.remove",
    "version.publish",
}


class ProjectActivityPostModel(OPModel):
    id: str | None = Field(None, description="Explicitly set the ID of the activity")
    activity_type: ActivityType = Field(..., example="comment")
    body: str = Field("", example="This is a comment")
    tags: list[str] | None = Field(None, example=["tag1", "tag2"])
    files: list[str] | None = Field(None, example=["file1", "file2"])
    timestamp: datetime.datetime | None = Field(None, example="2021-01-01T00:00:00Z")
    data: dict[str, Any] | None = Field(
        None,
        example={"key": "value"},
        description="Additional data",
    )


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
        description=(
            "When true, append files to the existing ones. replace them otherwise"
        ),
    )
    data: dict[str, Any] | None = Field(None, example={"key": "value"})


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
    ) -> tuple[
        str,
        str,
        ActivityReferenceType,
        ReferencedEntityType,
        str | None,
        str | None,
        dict[str, Any],
        datetime.datetime,
    ]:
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.UTC)
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
        return hash((self.entity_type, self.entity_id, self.entity_name))

    def __str__(self):
        main: str = ""
        if self.entity_name:
            main = self.entity_name
        elif self.entity_id:
            main = self.entity_id
        return f"<ActivityReference {self.reference_type} {self.entity_type} {main}>"

    def __eq__(self, other):
        if isinstance(other, ActivityReferenceModel):
            return self.__hash__() == other.__hash__()
        return False
