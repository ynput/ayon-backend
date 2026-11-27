import asyncio
from collections.abc import Mapping
from unittest.mock import AsyncMock, patch

from ayon_server.activities.notification_delivery import (
    DEFAULT_INBOX_IMPORTANCE,
    ActivityNotification,
    InboxMessage,
    NotificationChannels,
    NotificationDelivery,
    dispatch_inbox_messages,
    get_inbox_importance,
    plan_inbox_messages,
)


def make_notification(
    activity_type: str = "comment",
    references: Mapping[str, str] | None = None,
) -> ActivityNotification:
    if references is None:
        references = {"alice": "mention", "bob": "relation", "carol": "watching"}
    return ActivityNotification(
        project_name="demo",
        activity_id="a" * 32,
        activity_type=activity_type,
        body="First line\nSecond line",
        author="dave",
        references=references,
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


def test_status_changes_are_not_important_by_default():
    notification = make_notification("status.change", {"alice": "mention"})
    assert plan_inbox_messages(notification, {}) == [
        InboxMessage(recipients=["alice"], important=False, desktop=None)
    ]


def test_channels_decide_what_is_important_and_who_may_show_a_system_notification():
    channels = {
        "alice": NotificationChannels(important=False, desktop=True),
        "bob": NotificationChannels(important=True, desktop=False),
        "carol": NotificationChannels(desktop=False),
    }
    assert plan_inbox_messages(make_notification(), channels) == [
        InboxMessage(recipients=["bob", "carol"], important=True, desktop=False),
        InboxMessage(recipients=["alice"], important=False, desktop=True),
    ]


def test_an_addon_can_make_a_status_change_important():
    notification = make_notification("status.change", {"alice": "watching"})
    channels = {"alice": NotificationChannels(important=True)}
    assert plan_inbox_messages(notification, channels) == [
        InboxMessage(recipients=["alice"], important=True, desktop=None)
    ]


def test_recipients_missing_from_the_channels_get_the_defaults():
    channels = {"alice": NotificationChannels(important=False)}
    assert plan_inbox_messages(make_notification(), channels) == [
        InboxMessage(recipients=["carol"], important=True, desktop=None),
        InboxMessage(recipients=["alice", "bob"], important=False, desktop=None),
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


def test_inbox_importance_is_ayons_rule_by_default_and_after_a_failure():
    important = f"(({DEFAULT_INBOX_IMPORTANCE}) IS TRUE)"
    assert asyncio.run(get_inbox_importance("alice", important=True)) == important
    with patch.object(
        NotificationDelivery, "get_inbox_importance", AsyncMock(side_effect=ValueError)
    ):
        assert asyncio.run(get_inbox_importance("alice", important=True)) == important


def test_the_two_parts_of_the_inbox_leave_no_row_out():
    condition = "t.activity_type IN ('comment', 'version.publish')"
    with patch.object(
        NotificationDelivery, "get_inbox_importance", AsyncMock(return_value=condition)
    ):
        assert asyncio.run(get_inbox_importance("alice", important=True)) == (
            f"(({condition}) IS TRUE)"
        )
        assert asyncio.run(get_inbox_importance("alice", important=False)) == (
            f"(({condition}) IS NOT TRUE)"
        )
