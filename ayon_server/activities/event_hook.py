"""ActivityFeedEventHook

This module contains the ActivityFeedEventHook class which is responsible for
subscribing to events and creating activities in the database based on the
event data (such as status changes, assignee changes, etc).

Basically, it translates volatile, global events into persistent, project-specific
activities that are stored in the project schema in the database.

ActivityFeedEventHook.install() is called when server is started
(from ayon_server.api.server) and subscribes to the events that are relevant.
"""

__all__ = ["ActivityFeedEventHook"]

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar

from ayon_server.activities.create_activity import create_activity
from ayon_server.activities.watchers.set_watchers import (
    ensure_not_watching,
    ensure_watching,
)
from ayon_server.activities.watchers.watcher_list import build_watcher_list
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.postgres import Postgres

if TYPE_CHECKING:
    from ayon_server.events import EventModel, EventStream


class ActivityFeedEventHook:
    topics: ClassVar[dict[str, Callable[["EventModel"], Awaitable[None]]]]

    @classmethod
    def install(cls, event_stream: type["EventStream"]):
        """Subscribe to events that are relevant for the activity feed.

        This method is called once, when the server is started.
        EventStream class then calls the appropriate handlers
        when new events are published.
        """
        cls.topics = {
            "entity.folder.status_changed": cls.handle_status_changed,
            "entity.task.status_changed": cls.handle_status_changed,
            "entity.version.status_changed": cls.handle_status_changed,
            "entity.product.status_changed": cls.handle_status_changed,
            "entity.task.assignees_changed": cls.handle_assignees_changed,
            "entity.version.created": cls.handle_version_created,
        }
        for topic, handler in cls.topics.items():
            event_stream.subscribe(topic, handler)

    @classmethod
    async def handle_status_changed(cls, event: "EventModel"):
        entity_type = event.topic.split(".")[1]
        entity_class = get_entity_class(entity_type)
        assert event.project is not None, "Project is required for activities"
        entity = await entity_class.load(event.project, event.summary["entityId"])

        old_value = event.payload.get("oldValue")
        new_value = event.payload.get("newValue")

        origin_link = f"[{entity.name}]({entity_type}:{entity.id})"
        body = f"{origin_link} status changed from {old_value} to {new_value}"

        await create_activity(
            entity,
            activity_type="status.change",
            body=body,
            user_name=event.user,
            data={
                "oldValue": old_value,
                "newValue": new_value,
            },
        )

    @classmethod
    async def handle_assignees_changed(cls, event: "EventModel"):
        assert event.project is not None
        entity_class = get_entity_class("task")
        entity = await entity_class.load(event.project, event.summary["entityId"])

        old_value = event.payload.get("oldValue", [])
        new_value = event.payload.get("newValue", [])

        added = set(new_value) - set(old_value)
        removed = set(old_value) - set(new_value)

        all_assignees = list(set(old_value) | set(new_value))

        # Get all assignees full names

        if not all_assignees:
            return  # this shouldn't happen, but let's keep mypy happy

        name_tags: dict[str, str] = {
            name: f"[{name}](user:{name})" for name in all_assignees
        }
        q = """
            SELECT name, attrib->>'fullName' as full_name
            FROM users WHERE name = ANY($1)
            AND attrib->>'fullName' IS NOT NULL
        """

        async for row in Postgres.iterate(q, all_assignees):
            if not row["full_name"]:
                continue
            name_tag = f"[{row['full_name']}](user:{row['name']})"
            name_tags[row["name"]] = name_tag

        # create activities

        entity_tag = f"[{entity.name}](task:{entity.id})"

        for assignee in added:
            await ensure_watching(entity, assignee)
            name_tag = name_tags[assignee]
            await create_activity(
                entity,
                activity_type="assignee.add",
                body=f"Added {name_tag} to {entity_tag}",
                user_name=event.user,
                data={"assignee": assignee},
            )

        for assignee in removed:
            await ensure_not_watching(entity, assignee)
            name_tag = name_tags[assignee]
            await create_activity(
                entity,
                activity_type="assignee.remove",
                body=f"Removed {name_tag} from {entity_tag}",
                user_name=event.user,
                data={"assignee": assignee},
            )

    @classmethod
    async def handle_version_created(cls, event: "EventModel"):
        assert event.project is not None

        version_id = event.summary["entityId"]
        version = await get_entity_class("version").load(event.project, version_id)

        res = await Postgres.fetch(
            f"""
            SELECT
            p.id product_id,
            p.name product_name,
            p.product_type product_type,

            h.id folder_id,
            f.name folder_name,
            f.label folder_label,
            h.path folder_path,

            t.id task_id,
            t.name task_name,
            t.label task_label,
            t.task_type task_type

            FROM project_{event.project}.versions v
            INNER JOIN project_{event.project}.products p ON v.product_id = p.id
            INNER JOIN project_{event.project}.hierarchy h ON p.folder_id = h.id
            INNER JOIN project_{event.project}.folders f ON p.folder_id = f.id
            LEFT JOIN project_{event.project}.tasks t ON v.task_id = t.id

            WHERE v.id = $1

            """,
            version_id,
        )

        row = res[0]

        if event.user:
            await ensure_watching(version, event.user)
        if version.author and version.author != event.user:
            await ensure_watching(version, version.author)

        # add watchers from tasks

        query = f"""
            SELECT activity_data->>'watcher' as watcher
            FROM project_{event.project}.activity_feed
            WHERE activity_type = 'watch'
            AND reference_type = 'origin'
            AND entity_type = 'task'
            AND entity_id = $1
        """

        res = await Postgres.fetch(query, row["task_id"])
        task_watchers = [row["watcher"] for row in res]
        for watcher in task_watchers:
            await create_activity(
                entity=version,
                activity_type="watch",
                body="",
                user_name=watcher,
                data={"watcher": watcher},
            )
        await build_watcher_list(version)

        await create_activity(
            version,
            activity_type="version.publish",
            body=f"Published [{version.name}](version:{version.id})",
            user_name=version.author or event.user,
            data={
                "context": {
                    "folderId": row["folder_id"],
                    "folderName": row["folder_name"],
                    "folderLabel": row["folder_label"],
                    "folderPath": row["folder_path"],
                    "productId": row["product_id"],
                    "productName": row["product_name"],
                    "productType": row["product_type"],
                    "taskId": row["task_id"],
                    "taskLabel": row["task_label"],
                    "taskName": row["task_name"],
                    "taskType": row["task_type"],
                }
            },
        )
