from datetime import datetime
from typing import Any

import strawberry

from ayon_server.graphql.nodes.common import ThumbnailInfo


@strawberry.type
class KanbanNode:
    project_name: str = strawberry.field()
    project_code: str = strawberry.field()
    id: str = strawberry.field()
    name: str = strawberry.field()
    label: str | None = strawberry.field()
    status: str = strawberry.field()
    tags: list[str] = strawberry.field()
    task_type: str = strawberry.field()
    assignees: list[str] = strawberry.field()
    updated_at: datetime = strawberry.field()
    created_at: datetime = strawberry.field()
    priority: str | None = strawberry.field(default=None)
    due_date: datetime | None = strawberry.field(default=None)
    folder_id: str = strawberry.field()
    folder_name: str = strawberry.field()
    folder_label: str | None = strawberry.field()
    folder_path: str = strawberry.field()
    thumbnail_id: str | None = strawberry.field(default=None)
    thumbnail: ThumbnailInfo | None = None
    has_reviewables: bool = strawberry.field(default=False)

    last_version_with_thumbnail_id: str | None = strawberry.field(default=None)
    last_version_with_reviewable_version_id: str | None = strawberry.field(default=None)
    last_version_with_reviewable_product_id: str | None = strawberry.field(default=None)


async def kanban_node_from_record(
    project_name: str | None,
    record: dict[str, Any],
    context: dict[str, Any],
) -> KanbanNode:
    record = dict(record)
    record.pop("cursor", None)

    project_name = record.pop("project_name", project_name)
    assert project_name, "project_name is required"

    due_date = record.pop("due_date", None)
    if isinstance(due_date, datetime):
        due_date = due_date.replace(tzinfo=None)
    elif isinstance(due_date, str):
        due_date = datetime.fromisoformat(due_date)
    record["due_date"] = due_date

    # priorities

    task_priority = record.pop("priority", None)
    project_priority = record.pop("project_priority", None)
    folder_priority = record.pop("folder_priority", None)

    thumbnail = None
    thumb_data = record.pop("thumbnail_info", None) or {}
    if record["thumbnail_id"]:
        thumbnail = ThumbnailInfo(
            id=record["thumbnail_id"],
            source_entity_type=thumb_data.get("sourceEntityType"),
            source_entity_id=thumb_data.get("sourceEntityId"),
            relation=thumb_data.get("relation"),
        )

    return KanbanNode(
        project_name=project_name,
        priority=task_priority or folder_priority or project_priority,
        thumbnail=thumbnail,
        **record,
    )


KanbanNode.from_record = staticmethod(kanban_node_from_record)  # type: ignore
