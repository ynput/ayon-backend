import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import EntityID, SQLTool, json_dumps


def create_id():
    return uuid.uuid1().hex


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
    sender: str | None = Field(None)
    project: str | None = Field(None)
    user: str | None = Field(None)
    depends_on: str | None = Field(None, **EntityID.META)
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
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row["id"],
            hash=row["hash"],
            topic=row["topic"],
            project=row["project_name"],
            user=row["user_name"],
            sender=row["sender"],
            depends_on=row["depends_on"],
            status=row["status"],
            retries=row["retries"],
            description=row["description"],
            payload=row["payload"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def dispatch_event(
    topic: str,
    *,
    sender: str | None = None,
    hash: str | None = None,
    project: str | None = None,
    user: str | None = None,
    depends_on: str | None = None,
    description: str | None = None,
    summary: dict | None = None,
    payload: dict | None = None,
    finished: bool = True,
    store: bool = True,
) -> str | None:
    if summary is None:
        summary = {}
    if payload is None:
        payload = {}
    if description is None:
        description = ""

    event_id = create_id()
    if hash is None:
        hash = f"{event_id}"

    status: str = "finished" if finished else "pending"
    progress: float = 100 if finished else 0.0

    event = EventModel(
        id=event_id,
        hash=hash,
        sender=sender,
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
                "id": str(event.id).replace("-", ""),
                "topic": event.topic,
                "project": event.project,
                "user": event.user,
                "dependsOn": str(event.depends_on).replace("-", ""),
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


async def update_event(
    event_id: str,
    sender: str | None = None,
    project_name: str | None = None,
    status: str | None = None,
    description: str | None = None,
    summary: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    progress: float | None = None,
    store: bool = True,
):

    new_data: dict[str, Any] = {"updated_at": datetime.now()}

    if sender is not None:
        new_data["sender"] = sender
    if project_name is not None:
        new_data["project_name"] = project_name
    if status is not None:
        new_data["status"] = status
    if description is not None:
        new_data["description"] = description
    if summary is not None:
        new_data["summary"] = summary
    if payload is not None:
        new_data["payload"] = payload

    if store:
        query = SQLTool.update("events", f"WHERE id = '{event_id}'", **new_data)

        query[0] = (
            query[0]
            + """
             RETURNING
                id,
                topic,
                project_name,
                user_name,
                depends_on,
                description,
                summary,
                status,
                sender,
                created_at,
                updated_at
        """
        )

    else:
        query = ["SELECT * FROM events WHERE id=$!", event_id]

    result = await Postgres.fetch(*query)
    for row in result:
        data = dict(row)
        if not store:
            data.update(new_data)
        message = {
            "id": data["id"],
            "topic": data["topic"],
            "project": data["project_name"],
            "user": data["user_name"],
            "dependsOn": data["depends_on"],
            "description": data["description"],
            "summary": data["summary"],
            "status": data["status"],
            "sender": data["sender"],
            "createdAt": data["created_at"],
            "updatedAt": data["updated_at"],
        }
        if progress is not None:
            message["progress"] = progress
        await Redis.publish(json_dumps(message))
        return True
    return False
