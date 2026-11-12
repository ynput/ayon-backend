"""How activity notifications reach the users an activity involves.

Every user an activity refers to (mentioned, watching, related to the entity)
gets an `inbox.message` event, and the same activities fill their inbox.
`NotificationDelivery` is where an addon changes that, in the same way
`ActivityCategories` lets an addon provide activity categories: the defaults here
keep AYON's own behaviour, an addon replaces the class methods when it is
installed and puts the originals back when it goes away.
"""

__all__ = [
    "ActivityNotification",
    "InboxMessage",
    "NotificationChannels",
    "NotificationDelivery",
    "dispatch_inbox_messages",
    "get_inbox_filter",
    "plan_inbox_messages",
]

from collections.abc import Mapping
from dataclasses import dataclass

from ayon_server.events.eventstream import EventStream
from ayon_server.logging import log_traceback

IMPORTANT_REFERENCE_TYPES = frozenset({"mention", "watching"})


@dataclass(frozen=True)
class NotificationChannels:
    """What one recipient gets for one activity."""

    inbox: bool = True
    """The activity is announced to the recipient's inbox (live update)."""

    desktop: bool | None = None
    """Whether the client may show a system notification or a toast.
    `None` leaves it to the client's own rules (important messages only,
    and only when the user enabled desktop notifications)."""


@dataclass(frozen=True)
class ActivityNotification:
    """A created activity and the users it involves."""

    project_name: str
    activity_id: str
    activity_type: str
    body: str
    author: str | None
    references: Mapping[str, frozenset[str]]
    """User name -> the reference types that bring the activity to that user
    (`mention`, `watching`, `relation`, ...). The author is never included."""


@dataclass(frozen=True)
class InboxMessage:
    """One `inbox.message` event."""

    recipients: list[str]
    important: bool
    desktop: bool | None


class NotificationDelivery:
    @classmethod
    async def get_channels(
        cls, notification: ActivityNotification
    ) -> Mapping[str, NotificationChannels]:
        """Decide how each recipient of a new activity is notified.

        Called once per created activity, after it was committed. An addon can
        also use it to deliver through channels of its own, e-mail for example.
        Recipients missing from the result get the defaults. An exception
        is logged and also leads to the defaults.
        """
        return {name: NotificationChannels() for name in notification.references}

    @classmethod
    async def get_inbox_filter(cls, user_name: str) -> str | None:
        """An SQL condition that leaves activities out of the user's inbox.

        It is added to the inbox query with AND, so it describes the rows to keep.
        The query reads `activity_feed`, one row per activity reference, as `t`
        (`t.activity_type`, `t.reference_type`, `t.active`, ...).
        """
        _ = user_name
        return None


def is_important(activity_type: str, reference_types: frozenset[str]) -> bool:
    return (
        bool(reference_types & IMPORTANT_REFERENCE_TYPES)
        and activity_type != "status.change"
    )


def plan_inbox_messages(
    notification: ActivityNotification,
    channels: Mapping[str, NotificationChannels],
) -> list[InboxMessage]:
    """Group the recipients that get the same `inbox.message` event."""

    groups: dict[tuple[bool, bool | None], list[str]] = {}
    for name, reference_types in notification.references.items():
        recipient_channels = channels.get(name, NotificationChannels())
        if not recipient_channels.inbox and not recipient_channels.desktop:
            continue
        key = (
            is_important(notification.activity_type, reference_types),
            recipient_channels.desktop,
        )
        groups.setdefault(key, []).append(name)

    # important messages first, as they were before addons could take part
    return [
        InboxMessage(recipients=recipients, important=important, desktop=desktop)
        for (important, desktop), recipients in sorted(
            groups.items(), key=lambda item: not item[0][0]
        )
    ]


async def dispatch_inbox_messages(
    notification: ActivityNotification,
    *,
    user_name: str | None,
) -> None:
    try:
        channels = await NotificationDelivery.get_channels(notification)
    except Exception:
        log_traceback("Notification delivery failed, using the default channels")
        channels = {}

    for message in plan_inbox_messages(notification, channels):
        summary: dict[str, object] = {
            "activityId": notification.activity_id,
            "activityType": notification.activity_type,
            "isImportant": message.important,
        }
        if message.desktop is not None:
            summary["desktopEnabled"] = message.desktop
        await EventStream.dispatch(
            "inbox.message",
            project=notification.project_name,
            description=notification.body.split("\n")[0],
            summary=summary,
            recipients=message.recipients,
            store=False,
            user=user_name,
        )


async def get_inbox_filter(user_name: str) -> str | None:
    """The addon's inbox condition, as it can be put in the inbox query."""
    try:
        condition = await NotificationDelivery.get_inbox_filter(user_name)
    except Exception:
        log_traceback("Inbox filter failed, showing the whole inbox")
        return None
    if not condition:
        return None
    # The query is an argument of get_user_inbox(), a string that function
    # formats into a query: its quotes are doubled once more.
    return f"({condition})".replace("'", "''")
