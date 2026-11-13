import asyncio
from collections.abc import Mapping
from unittest.mock import AsyncMock, patch

from ayon_server.activities.notification_delivery import (
    ActivityNotification,
    InboxMessage,
    NotificationChannels,
    NotificationDelivery,
    dispatch_inbox_messages,
    get_inbox_filter,
    plan_inbox_messages,
)


def make_notification(
    activity_type: str = "comment",
    references: Mapping[str, set[str]] | None = None,
) -> ActivityNotification:
    if references is None:
        references = {
            "alice": {"mention"},
            "bob": {"relation"},
            "carol": {"watching", "relation"},
        }
    return ActivityNotification(
        project_name="demo",
        activity_id="a" * 32,
        activity_type=activity_type,
        body="First line\nSecond line",
        author="dave",
        references={name: frozenset(types) for name, types in references.items()},
    )


def test_defaults_notify_everybody_and_leave_desktop_to_the_client():
    notification = make_notification()
    channels = asyncio.run(NotificationDelivery.get_channels(notification))
    assert set(channels) == {"alice", "bob", "carol"}
    assert all(c == NotificationChannels() for c in channels.values())

    assert plan_inbox_messages(notification, channels) == [
        InboxMessage(recipients=["alice", "carol"], important=True, desktop=None),
        InboxMessage(recipients=["bob"], important=False, desktop=None),
    ]


def test_status_changes_are_never_important():
    notification = make_notification("status.change", {"alice": {"mention"}})
    assert plan_inbox_messages(notification, {}) == [
        InboxMessage(recipients=["alice"], important=False, desktop=None)
    ]


def test_channels_decide_who_is_announced_and_who_may_show_a_system_notification():
    channels = {
        "alice": NotificationChannels(inbox=False, desktop=True),
        "bob": NotificationChannels(inbox=False, desktop=False),
        "carol": NotificationChannels(inbox=True, desktop=False),
    }
    assert plan_inbox_messages(make_notification(), channels) == [
        InboxMessage(recipients=["alice"], important=True, desktop=True),
        InboxMessage(recipients=["carol"], important=True, desktop=False),
    ]


def test_recipients_missing_from_the_channels_get_the_defaults():
    channels = {"alice": NotificationChannels(inbox=False)}
    assert plan_inbox_messages(make_notification(), channels) == [
        InboxMessage(recipients=["carol"], important=True, desktop=None),
        InboxMessage(recipients=["bob"], important=False, desktop=None),
    ]


def test_dispatch_sends_one_event_per_group():
    channels = {"alice": NotificationChannels(desktop=True)}
    dispatch = AsyncMock()
    with (
        patch.object(
            NotificationDelivery, "get_channels", AsyncMock(return_value=channels)
        ),
        patch("ayon_server.events.eventstream.EventStream.dispatch", dispatch),
    ):
        asyncio.run(dispatch_inbox_messages(make_notification(), user_name="dave"))

    calls = [(c.kwargs["recipients"], c.kwargs["summary"]) for c in dispatch.mock_calls]
    summary = {"activityId": "a" * 32, "activityType": "comment"}
    assert calls == [
        (["alice"], {**summary, "isImportant": True, "desktopEnabled": True}),
        (["carol"], {**summary, "isImportant": True}),
        (["bob"], {**summary, "isImportant": False}),
    ]
    for call in dispatch.mock_calls:
        assert call.args == ("inbox.message",)
        assert call.kwargs["description"] == "First line"
        assert call.kwargs["project"] == "demo"
        assert call.kwargs["user"] == "dave"
        assert call.kwargs["store"] is False


def test_failing_delivery_falls_back_to_the_defaults():
    dispatch = AsyncMock()
    with (
        patch.object(
            NotificationDelivery, "get_channels", AsyncMock(side_effect=ValueError)
        ),
        patch("ayon_server.events.eventstream.EventStream.dispatch", dispatch),
    ):
        asyncio.run(dispatch_inbox_messages(make_notification(), user_name="dave"))

    assert [c.kwargs["recipients"] for c in dispatch.mock_calls] == [
        ["alice", "carol"],
        ["bob"],
    ]


def test_inbox_filter_is_left_out_by_default_and_after_a_failure():
    assert asyncio.run(get_inbox_filter("alice")) is None
    with patch.object(
        NotificationDelivery, "get_inbox_filter", AsyncMock(side_effect=ValueError)
    ):
        assert asyncio.run(get_inbox_filter("alice")) is None


def test_inbox_filter_is_wrapped_and_escaped_for_the_inbox_query():
    condition = "t.activity_type IN ('comment', 'version.publish')"
    with patch.object(
        NotificationDelivery, "get_inbox_filter", AsyncMock(return_value=condition)
    ):
        assert asyncio.run(get_inbox_filter("alice")) == (
            "(t.activity_type IN (''comment'', ''version.publish''))"
        )
