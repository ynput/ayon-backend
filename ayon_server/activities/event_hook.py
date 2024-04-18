from typing import TYPE_CHECKING, Awaitable, Callable, ClassVar, Type

from ayon_server.activities.create_activity import create_activity
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.postgres import Postgres

if TYPE_CHECKING:
    from ayon_server.events import EventModel, EventStream


class ActivityFeedEventHook:
    topics: ClassVar[dict[str, Callable[["EventModel"], Awaitable[None]]]]

    @classmethod
    def install(cls, event_stream: Type["EventStream"]):
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

        added = set(new_value) - set(old_value)
        removed = set(old_value) - set(new_value)

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

        await create_activity(
            version,
            activity_type="version.publish",
            body=f"Published [{version.name}](version:{version.id})",
            user_name=version.author or event.user,
            data={
                "publish": {
                    "version": version.version,
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
