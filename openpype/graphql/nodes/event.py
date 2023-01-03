import strawberry

from openpype.utils import get_nickname, obscure


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
    created_at: float
    updated_at: float


def event_from_record(record: dict, context: dict) -> EventNode:
    current_user = context["user"]
    record = dict(record)

    if current_user.is_guest and record["user_name"] != current_user.name:
        if record["user_name"]:
            record["user_name"] = get_nickname(record["user_name"])
        if record["description"]:
            record["description"] = obscure(record["description"])

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
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(EventNode, "from_record", staticmethod(event_from_record))
