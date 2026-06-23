import datetime
from typing import Annotated, Any, Literal

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
    "version.review",
    "attrib.change",
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
    id: Annotated[
        str | None, Field(description="Explicitly set the ID of the activity")
    ] = None

    activity_type: Annotated[
        ActivityType,
        Field(
            example="comment",
        ),
    ]

    body: Annotated[
        str,
        Field(
            example="This is a comment",
        ),
    ] = ""

    tags: Annotated[
        list[str] | None,
        Field(
            example=["tag1", "tag2"],
        ),
    ] = None

    files: Annotated[
        list[str] | None,
        Field(
            example=["file1", "file2"],
        ),
    ] = None

    timestamp: Annotated[
        datetime.datetime | None, Field(example="2021-01-01T00:00:00Z")
    ] = None

    data: Annotated[
        dict[str, Any] | None,
        Field(
            example={"key": "value"},
            description="Additional data",
        ),
    ] = None


class ActivityPatchModel(OPModel):
    body: Annotated[
        str | None,
        Field(
            example="This is a comment",
            description="When set, update the activity body",
        ),
    ] = None

    tags: Annotated[
        list[str] | None,
        Field(
            title="Tags",
            description="When set, update the activity tags",
            example=["tag1", "tag2"],
        ),
    ] = None

    files: Annotated[
        list[str] | None,
        Field(
            title="Files",
            description="When set, update the activity files",
            example=["file1", "file2"],
        ),
    ] = None

    append_files: Annotated[
        bool,
        Field(
            title="Append files",
            description=(
                "When true, append files to the existing ones. replace them otherwise"
            ),
            example=False,
        ),
    ] = False

    data: Annotated[
        dict[str, Any] | None,
        Field(
            title="Additional data",
            example={"key": "value"},
        ),
    ] = None


class ActivityReferenceModel(OPModel):
    id: str = Field(default_factory=create_uuid)
    reference_type: ActivityReferenceType = Field(example="mention")
    entity_type: ReferencedEntityType = Field(example="task")
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

    def __hash__(self) -> int:
        return hash((self.entity_type, self.entity_id, self.entity_name))

    def __str__(self) -> str:
        main: str = ""
        if self.entity_name:
            main = self.entity_name
        elif self.entity_id:
            main = self.entity_id
        return f"<ActivityReference {self.reference_type} {self.entity_type} {main}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ActivityReferenceModel):
            return self.__hash__() == other.__hash__()
        return False
