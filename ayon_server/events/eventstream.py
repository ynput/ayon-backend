from datetime import datetime
from typing import Any, Callable, Coroutine, Type

from ayon_server.exceptions import ConstraintViolationException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.utils import SQLTool, json_dumps

from .base import EventModel, EventStatus, create_id

HandlerType = Callable[[EventModel], Coroutine[None, None, None]]


class EventStream:
    model: Type[EventModel] = EventModel
    hooks: dict[str, list[HandlerType]] = {}

    @classmethod
    def register_hook(cls, topic: str, handler: HandlerType) -> None:
        if topic not in cls.hooks:
            cls.hooks[topic] = []
        cls.hooks[topic].append(handler)

    @classmethod
    async def dispatch(
        cls,
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
    ) -> str:
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
            retries=0,
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
            except Postgres.ForeignKeyViolationError as e:
                raise ConstraintViolationException(
                    "Event depends on non-existing event"
                ) from e

            except Postgres.UniqueViolationError as e:
                raise ConstraintViolationException(
                    "Event with same hash already exists"
                ) from e

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

        handlers = cls.hooks.get(event.topic, [])
        for handler in handlers:
            await handler(event)

        return event.id

    @classmethod
    async def update(
        cls,
        event_id: str,
        *,
        sender: str | None = None,
        project: str | None = None,
        user: str | None = None,
        status: EventStatus | None = None,
        description: str | None = None,
        summary: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        progress: float | None = None,
        store: bool = True,
        retries: int | None = None,
    ) -> bool:
        new_data: dict[str, Any] = {"updated_at": datetime.now()}

        if sender is not None:
            new_data["sender"] = sender
        if project is not None:
            new_data["project_name"] = project
        if status is not None:
            new_data["status"] = status
        if description is not None:
            new_data["description"] = description
        if summary is not None:
            new_data["summary"] = summary
        if payload is not None:
            new_data["payload"] = payload
        if retries is not None:
            new_data["retries"] = retries
        if user is not None:
            new_data["user_name"] = user

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
            query = ["SELECT * FROM events WHERE id=$1", event_id]

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
