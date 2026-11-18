"""How activity notifications reach the users an activity involves.

Every user an activity refers to (mentioned, watching, related to the entity)
gets an `inbox.message` event, and the same activities fill their inbox, split
into an important part and the rest. `NotificationDelivery` is where an addon
changes that, in the same way `ActivityCategories` lets an addon provide activity
categories: the defaults here keep AYON's own behaviour, an addon replaces the
class methods when it is installed and puts the originals back when it goes away.
"""

__all__ = [
    "DEFAULT_INBOX_IMPORTANCE",
    "ActivityNotification",
    "InboxMessage",
    "NotificationChannels",
    "NotificationDelivery",
    "dispatch_inbox_messages",
    "get_inbox_importance",
    "is_important",
    "plan_inbox_messages",
]

from collections.abc import Mapping
from dataclasses import dataclass, field

from ayon_server.events.eventstream import EventStream
from ayon_server.logging import log_traceback

IMPORTANT_REFERENCE_TYPES = frozenset({"mention", "watching"})

# The same rule as is_important(), for a row of activity_feed read as `t`
DEFAULT_INBOX_IMPORTANCE = (
    "t.reference_type IN ('mention', 'watching') AND t.activity_type != 'status.change'"
)


@dataclass(frozen=True)
class NotificationChannels:
    """What one recipient gets for one activity."""

    important: bool | None = None
    """Whether the activity is announced as an important message.
    `None` keeps AYON's own rule. It has to agree with `get_inbox_importance`,
    which splits the stored inbox of the same user."""

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
    references: Mapping[str, str]
    """User name -> the reference type that brings the activity to that user.
    A user has one reference per activity: `mention` before `watching` before
    `relation`. Authors are left out, except a guest author, who has no
    reference of their own: compare with `author`."""
    roles: Mapping[str, str] = field(default_factory=dict)
    """User name -> how the user is related to the entity: `assignee`, or
    `author` of the version. Users who are not related to it are left out.
    The reference of the user stores it as `data.role`, whatever its type."""


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
    async def get_inbox_importance(cls, user_name: str) -> str | None:
        """An SQL condition that is true for the important rows of a user's inbox.

        The rows it is not true for are the other part of the inbox, so every
        row stays in one of the two. The condition is evaluated on a row of
        `activity_feed`, one row per activity reference, read as `t`
        (`t.activity_type`, `t.reference_type`, ...). `None` keeps AYON's rule.
        """
        _ = user_name
        return None


def is_important(activity_type: str, reference_type: str) -> bool:
    return (
        reference_type in IMPORTANT_REFERENCE_TYPES and activity_type != "status.change"
    )


def plan_inbox_messages(
    notification: ActivityNotification,
    channels: Mapping[str, NotificationChannels],
) -> list[InboxMessage]:
    """Group the recipients that get the same `inbox.message` event."""

    groups: dict[tuple[bool, bool | None], list[str]] = {}
    for name, reference_type in notification.references.items():
        recipient_channels = channels.get(name, NotificationChannels())
        important = recipient_channels.important
        if important is None:
            important = is_important(notification.activity_type, reference_type)
        groups.setdefault((important, recipient_channels.desktop), []).append(name)

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


async def get_inbox_importance(user_name: str, *, important: bool) -> str:
    """The condition for the important (or the other) part of a user's inbox.

    For a query that reads `activity_feed` as `t`.
    """
    try:
        condition = await NotificationDelivery.get_inbox_importance(user_name)
    except Exception:
        log_traceback("Inbox importance failed, using the default split")
        condition = None
    # IS NOT TRUE, so a row the condition is unknown for is not lost
    operator = "IS TRUE" if important else "IS NOT TRUE"
    return f"(({condition or DEFAULT_INBOX_IMPORTANCE}) {operator})"
