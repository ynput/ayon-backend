import uuid

import strawberry


@strawberry.type
class EventNode:
    id: uuid.UUID
    hash: uuid.UUID
    topic: str
    project: str | None
    user: str | None
    sender: str | None
    status: str
    retries: int
    description: str
    created_at: float
    updated_at: float


def event_from_record(record: dict, context: dict) -> EventNode:
    return EventNode(
        id=record["id"],
        hash=record["hash"],
        topic=record["topic"],
        project=record["project_name"],
        user=record["user_name"],
        sender=record["sender"],
        status=record["status"],
        retries=record["retries"],
        description=record["description"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(EventNode, "from_record", staticmethod(event_from_record))
