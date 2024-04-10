from typing import TYPE_CHECKING

from ayon_server.activities.create_activity import create_activity
from ayon_server.helpers.get_entity_class import get_entity_class

if TYPE_CHECKING:
    from ayon_server.events import EventModel, EventStream


class ActivityFeedEventHook:
    @classmethod
    def install(cls, event_stream: "EventStream"):
        cls.topics = {
            "entity.folder.status_changed": cls.handle_status_changed,
            "entity.task.status_changed": cls.handle_status_changed,
            "entity.version.status_changed": cls.handle_status_changed,
            "entity.product.status_changed": cls.handle_status_changed,
            "entity.task.assignees_changed": cls.handle_assignees_changed,
        }
        for topic, handler in cls.topics.items():
            event_stream.subscribe(topic, handler)

    @classmethod
    async def handle_status_changed(cls, event: "EventModel"):
        entity_type = event.topic.split(".")[1]
        entity_class = get_entity_class(entity_type)  # type: ignore
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
        entity_class = get_entity_class("task")  # type: ignore
        entity = await entity_class.load(event.project, event.summary["entityId"])

        old_value = event.payload.get("oldValue", [])
        new_value = event.payload.get("newValue", [])

        print(f"Old value: {old_value}")

        added = set(new_value) - set(old_value)
        removed = set(old_value) - set(new_value)

        print(f"Added: {added}")
        print(f"Removed: {removed}")

        for assignee in added:
            await create_activity(
                entity,
                activity_type="assignee.add",
                body=f"Added {assignee} to [{entity.name}](task:{entity.id})",
                user_name=event.user,
                data={"assignee": assignee},
            )

        for assignee in removed:
            await create_activity(
                entity,
                activity_type="assignee.remove",
                body=f"Removed {assignee} from [{entity.name}](task:{entity.id})",
                user_name=event.user,
                data={"assignee": assignee},
            )
