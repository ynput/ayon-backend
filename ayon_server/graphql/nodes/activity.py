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
class ActivityOriginNode:
    type: str = strawberry.field()
    id: str = strawberry.field()
    name: str = strawberry.field(default=None)
    label: str | None = strawberry.field(default=None)

    @property
    def markdownlink(self) -> str:
        return f"[{self.name}]({self.type}:{self.id})"

    @strawberry.field
    def link(self) -> str:
        return self.markdownlink


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
    active: bool = strawberry.field(default=True)

    origin: ActivityOriginNode | None = strawberry.field()

    @strawberry.field
    async def author(self, info: Info) -> Optional[UserNode]:
        data = json_loads(self.activity_data)
        if "author" in data:
            author = data["author"]
            loader = info.context["user_loader"]
            record = await loader.load(author)
            return info.context["user_from_record"](record, info.context)
        return None


def replace_reference_body(node: ActivityNode) -> ActivityNode:
    if not node.origin:
        return node  # should not happen

    if node.reference_type == "mention":
        node.body = (
            f"mentioned in a {node.activity_type} " f"on {node.origin.markdownlink}"
        )
        return node

    if node.reference_type == "relation":
        if node.activity_type == "comment":
            r = "commented on"
        elif node.activity_type == "status_change":
            r = "changed status of"
        node.body = f"{r} a related {node.origin.markdownlink}"

        return node
    return node


def activity_from_record(
    project_name: str, record: dict, context: dict
) -> ActivityNode:
    """Construct a folder node from a DB row."""

    record = dict(record)
    record.pop("cursor", None)

    activity_data = record.pop("activity_data", {})
    reference_data = record.pop("reference_data", {})

    origin_data = activity_data.get("origin")
    if origin_data:
        origin = ActivityOriginNode(**origin_data)
    else:
        origin = None

    node = ActivityNode(
        project_name=project_name,
        activity_data=json_dumps(activity_data),
        reference_data=json_dumps(reference_data),
        origin=origin,
        **record,
    )
    # probably won't be used
    # node = replace_reference_body(node)
    return node


ActivityNode.from_record = staticmethod(activity_from_record)  # type: ignore
