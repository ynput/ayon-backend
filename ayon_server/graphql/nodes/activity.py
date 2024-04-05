from datetime import datetime
from typing import TYPE_CHECKING, Optional

import strawberry
from strawberry import LazyType
from strawberry.types import Info

from ayon_server.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from ayon_server.graphql.nodes.user import UserNode
else:
    UserNode = LazyType["UserNode", ".user"]


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

    origin_type: str | None = strawberry.field()
    origin_id: str | None = strawberry.field()

    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()
    creation_order: int = strawberry.field()

    activity_type: str = strawberry.field()
    body: str = strawberry.field()
    activity_data: str = strawberry.field()
    reference_data: str = strawberry.field()
    active: bool = strawberry.field(default=True)

    @strawberry.field
    async def author(self, info: Info) -> Optional[UserNode]:
        data = json_loads(self.activity_data)
        if "author" in data:
            author = data["author"]
            loader = info.context["user_loader"]
            record = await loader.load(author)
            return info.context["user_from_record"](record, info.context)


def activity_from_record(
    project_name: str, record: dict, context: dict
) -> ActivityNode:
    """Construct a folder node from a DB row."""

    record = dict(record)
    record.pop("cursor", None)

    activity_data = record.pop("activity_data", {})
    reference_data = record.pop("reference_data", {})

    return ActivityNode(
        project_name=project_name,
        activity_data=json_dumps(activity_data),
        reference_data=json_dumps(reference_data),
        origin_type=activity_data.get("origin_type"),
        origin_id=activity_data.get("origin_id"),
        **record,
    )


ActivityNode.from_record = staticmethod(activity_from_record)  # type: ignore
