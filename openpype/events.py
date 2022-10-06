import time
import uuid
from typing import Any, Literal

from pydantic import Field

from openpype.lib.postgres import Postgres
from openpype.lib.redis import Redis
from openpype.types import OPModel
from openpype.utils import SQLTool, json_dumps


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

    id: uuid.UUID = Field(default_factory=uuid.uuid1)
    hash: str = Field(...)
    topic: str = Field(...)
    sender: str | None = Field(None)
    project: str | None = Field(None)
    user: str | None = Field(None)
    depends_on: uuid.UUID | None = Field(None)
    status: Literal[
        "pending",
        "in_progress",
        "finished",
        "failed",
        "aborted",
        "restarted",
    ] = Field("pending")
    retries: int = Field(0)
    description: str = Field(...)
    summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


async def dispatch_event(
    topic: str,
    *,
    sender: str | None = None,
    hash: str | None = None,
    project: str | None = None,
    user: str | None = None,
    depends_on: uuid.UUID | None = None,
    description: str | None = None,
    summary: dict | None = None,
    payload: dict | None = None,
    finished: bool = True,
    store: bool = True,
) -> uuid.UUID | None:
    if summary is None:
        summary = {}
    if payload is None:
        payload = {}
    if description is None:
        description = ""

    event_id = uuid.uuid1()
    if hash is None:
        hash = f"{event_id}"

    status: str = "finished" if finished else "pending"
    progress: float = 100 if finished else 0.0

    event = EventModel(
        id=event_id,
        hash=hash,
        topic=topic,
        project=project,
        user=user,
        depends_on=depends_on,
        status=status,
        description=description,
        summary=summary,
        payload=payload,
    )

    if store:
        query = SQLTool.insert(
            table="events",
            id=event.id,
            hash=event.hash,
            sender=event.sender,
            topic=event.topic,
            project_name=event.project,
            user_name=event.user,
            depends_on=depends_on,
            status=status,
            description=description,
            summary=event.summary,
            payload=event.payload,
        )
        try:
            await Postgres.execute(*query)
        except Postgres.ForeignKeyViolationError:
            print(f"Unable to dispatch {event.topic}")
            return None

    await Redis.publish(
        json_dumps(
            {
                "id": event.id,
                "topic": event.topic,
                "project": event.project,
                "user": event.user,
                "description": event.description,
                "summary": event.summary,
                "status": event.status,
                "progress": progress,
                "sender": sender,
                "store": store,  # useful to allow querying details
                "createdAt": event.created_at,
                "updatedAt": event.updated_at,
            }
        )
    )

    return event.id
