import time
import uuid
from typing import Any, Literal

from pydantic import Field

from openpype.lib.postgres import Postgres
from openpype.lib.redis import Redis
from openpype.types import OPModel
from openpype.utils import SQLTool, json_dumps


class EventModel(OPModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid1)
    hash: str = Field(...)
    topic: str = Field(...)
    project: str | None = Field(None)
    user: str | None = Field(None)
    dependencies: list[uuid.UUID] = Field(default_factory=list)
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
    dependencies: list[uuid.UUID] | None = None,
    description: str | None = None,
    summary: dict | None = None,
    payload: dict | None = None,
    finished: bool = True,
    store: bool = True,
):
    if dependencies is None:
        dependencies = []
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
        dependencies=dependencies,
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
            topic=event.topic,
            project_name=event.project,
            user_name=event.user,
            dependencies=dependencies,
            status=status,
            description=description,
            summary=event.summary,
            payload=event.payload,
        )
        try:
            await Postgres.execute(*query)
        except Postgres.ForeignKeyViolationError:
            print(f"Unable to dispatch {event.topic}")

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
