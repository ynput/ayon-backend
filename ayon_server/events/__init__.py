__all__ = [
    "EventStream",
    "EventModel",
    "EventStatus",
    "HandlerType",
    "dispatch_event",
    "update_event",
]

from typing import Any

from ayon_server.events.base import EventModel, EventStatus, HandlerType
from ayon_server.events.eventstream import EventStream


async def dispatch_event(
    topic: str,
    *,
    sender: str | None = None,
    sender_type: str | None = None,
    hash: str | None = None,
    project: str | None = None,
    user: str | None = None,
    depends_on: str | None = None,
    description: str | None = None,
    summary: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    finished: bool = True,
    store: bool = True,
    reuse: bool = False,
) -> str:
    """Dispatch an event to the event stream.

    This function is deprecated and is provided only to
    maintain backwards compatibility with older addons.

    Use `EventStream.dispatch` instead.
    """
    return await EventStream.dispatch(
        topic=topic,
        sender=sender,
        sender_type=sender_type,
        hash=hash,
        project=project,
        user=user,
        depends_on=depends_on,
        description=description,
        summary=summary,
        payload=payload,
        finished=finished,
        store=store,
        reuse=reuse,
    )


async def update_event(
    event_id: str,
    *,
    sender: str | None = None,
    sender_type: str | None = None,
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
    """Update an event in the event stream.

    This function is deprecated and is provided only to
    maintain backwards compatibility with older addons.

    Use `EventStream.update` instead.

    """
    return await EventStream.update(
        event_id=event_id,
        sender=sender,
        sender_type=sender_type,
        project=project,
        user=user,
        status=status,
        description=description,
        summary=summary,
        payload=payload,
        progress=progress,
        store=store,
        retries=retries,
    )
