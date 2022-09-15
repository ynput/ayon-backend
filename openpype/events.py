import time
import uuid
from typing import Any, Literal

from pydantic import Field

from openpype.lib.redis import Redis
from openpype.types import OPModel
from openpype.utils import json_dumps


class Event(OPModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid1)
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
    summary: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


async def dispatch_event(
    topic: str,
    *,
    sender: str | None = None,
    project: str | None = None,
    user: str | None = None,
    dependencies: list[uuid.UUID] | None = None,
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

    status: str = "finished" if finished else "pending"
    progress: float = 100 if finished else 0.0

    event = Event(
        topic=topic,
        project=project,
        user=user,
        dependencies=dependencies,
        status=status,
        summary=summary,
        payload=payload,
    )

    if store:
        # TODO: save the event
        pass

    await Redis.publish(
        json_dumps(
            {
                "topic": event.topic,
                "project": event.project,
                "user": event.user,
                "summary": event.summary,
                "status": event.status,
                "progress": progress,
                "sender": sender,
            }
        )
    )

    return event.id
