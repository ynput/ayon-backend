import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from ayon_server.events.typing import (
    DEPENDS_ON_FIELD,
    DESCRIPTION_FIELD,
    PAYLOAD_FIELD,
    PROJECT_FIELD,
    SENDER_FIELD,
    SUMMARY_FIELD,
    USER_FIELD,
)
from ayon_server.types import Field, OPModel
from ayon_server.utils import EntityID


def create_id():
    return uuid.uuid1().hex


EventStatus = Literal[
    "pending",
    "in_progress",
    "finished",
    "failed",
    "aborted",
    "restarted",
]


class EventModel(OPModel):
    """
    ID is an automatically assigned primary identifier of the event.
    Apart from uniqueness, it does not have any special meaning. But it is used
    for dependencies and hashing.

    Hash is an unique value for an evend, which is per-topic deterministic.
    This prevents storing two identical events by two different dispatchers.
    For example 'enroll' endpoint, which is responsible to create new processing
    jobs uses hash of source event id and the target topic. that effectively
    prevents two services starting the same job.

    Depends_on is nullable field, when used, it contains an ID of previously
    finished event which this event depends.
    TBD: when a dependency is restarted, should all dependent
    events be restarted as well?

    """

    id: str = Field(default_factory=create_id, **EntityID.META)
    hash: str = Field(...)
    topic: str = Field(...)
    sender: str | None = SENDER_FIELD
    sender_type: str | None = Field(None)
    project: str | None = PROJECT_FIELD
    user: str | None = USER_FIELD
    depends_on: str | None = DEPENDS_ON_FIELD
    status: EventStatus = Field("pending")
    retries: int = Field(0)
    description: str | None = DESCRIPTION_FIELD
    summary: dict[str, Any] = SUMMARY_FIELD
    payload: dict[str, Any] = PAYLOAD_FIELD
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EventModel":
        return cls(
            id=row["id"],
            hash=row["hash"],
            topic=row["topic"],
            project=row["project_name"],
            user=row["user_name"],
            sender=row["sender"],
            sender_type=row["sender_type"],
            depends_on=row["depends_on"],
            status=row["status"],
            retries=row["retries"],
            description=row["description"],
            payload=row["payload"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


HandlerType = Callable[[EventModel], Awaitable[None]]
