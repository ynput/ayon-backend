from datetime import datetime

import strawberry

from ayon_server.utils import json_dumps


@strawberry.type
class ActivityNode:
    project_name: str = strawberry.field()

    reference_id: str = strawberry.field()
    activity_id: str = strawberry.field()
    reference_type: str = strawberry.field()

    entity_type: str = strawberry.field()  # TODO. use literal?
    entity_id: str | None = strawberry.field()
    entity_name: str | None = strawberry.field()
    entity_path: str | None = strawberry.field()

    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()
    creation_order: int = strawberry.field()

    activity_type: str = strawberry.field()
    body: str = strawberry.field()
    activity_data: str = strawberry.field()
    reference_data: str = strawberry.field()
    active: bool = strawberry.field()


def activity_from_record(
    project_name: str, record: dict, context: dict
) -> ActivityNode:
    """Construct a folder node from a DB row."""

    activity_data = record.pop("activity_data")
    reference_data = record.pop("reference_data")

    return ActivityNode(
        project_name=project_name,
        activity_data=json_dumps(activity_data),
        reference_data=json_dumps(reference_data),
        **record,
    )


ActivityNode.from_record = staticmethod(activity_from_record)  # type: ignore
