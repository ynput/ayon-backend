from datetime import datetime
from typing import Any

import strawberry

from ayon_server.utils import json_dumps


@strawberry.type
class EventNode:
    id: str
    hash: str
    topic: str
    project: str | None
    user: str | None
    sender: str | None
    depends_on: str | None
    status: str
    retries: int
    description: str
    summary: str
    created_at: datetime
    updated_at: datetime
    data: str | None
    payload: str | None


async def event_from_record(
    project_name: str | None,
    record: dict[str, Any],
    context: dict[str, Any],
) -> EventNode:
    record = dict(record)
    data = record.get("data", {})
    payload = record.get("payload", {})

    return EventNode(
        id=record["id"],
        hash=record["hash"],
        topic=record["topic"],
        project=record["project_name"],
        user=record["user_name"],
        sender=record["sender"],
        depends_on=record["depends_on"],
        status=record["status"],
        retries=record["retries"],
        description=record["description"],
        summary=json_dumps(record["summary"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        data=json_dumps(data) if data else None,  # deprecated, to be removed
        payload=json_dumps(payload) if payload else None,
    )


EventNode.from_record = staticmethod(event_from_record)  # type: ignore
