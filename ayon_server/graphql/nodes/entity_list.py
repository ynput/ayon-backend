from datetime import datetime
from typing import Any

import strawberry

from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.types import BaseConnection, BaseEdge, Info
from ayon_server.utils import json_dumps

#
# Entity list item
#


@strawberry.type
class EntityListItemEdge(BaseEdge):
    id: str = strawberry.field()
    project_name: str = strawberry.field()

    entity_type: str = strawberry.field()
    entity_id: str = strawberry.field()
    position: int = strawberry.field(default=0)

    attrib: str = strawberry.field(default="{}")
    data: str = strawberry.field(default="{}")

    tags: list[str] = strawberry.field(default_factory=list)

    created_by: str | None = strawberry.field(default=None)
    updated_by: str | None = strawberry.field(default=None)
    created_at: datetime = strawberry.field(default=None)
    updated_at: datetime = strawberry.field(default=None)

    cursor: str | None = strawberry.field(default=None)

    @strawberry.field(description="Item node")
    async def node(self, info: Info) -> "BaseNode":
        if self.entity_type == "folder":
            loader = info.context["folder_loader"]
            parser = info.context["folder_from_record"]
        elif self.entity_type == "version":
            loader = info.context["version_loader"]
            parser = info.context["version_from_record"]
        elif self.entity_type == "product":
            loader = info.context["product_loader"]
            parser = info.context["product_from_record"]
        elif self.entity_type == "task":
            loader = info.context["task_loader"]
            parser = info.context["task_from_record"]
        elif self.entity_type == "representation":
            loader = info.context["representation_loader"]
            parser = info.context["representation_from_record"]
        else:
            raise ValueError
        record = await loader.load((self.project_name, self.entity_id))
        return parser(self.project_name, record, info.context)

    @classmethod
    def from_record(
        cls,
        project_name: str,
        record: dict[str, Any],
        context: dict[str, Any],
    ) -> "EntityListItemEdge":
        return cls(
            project_name=project_name,
            id=record["id"],
            entity_type=record["entity_type"],
            entity_id=record["entity_id"],
            position=record["position"],
            attrib=json_dumps(record["attrib"]),
            data=json_dumps(record["data"]),
            tags=record["tags"],
            created_by=record["created_by"],
            updated_by=record["updated_by"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            cursor=record["cursor"],
        )


@strawberry.type
class EntityListItemsConnection(BaseConnection):
    edges: list[EntityListItemEdge] = strawberry.field(default_factory=list)


#
# Entity list
#


@strawberry.type
class EntityListNode:
    project_name: str = strawberry.field()

    id: str = strawberry.field()

    label: str = strawberry.field()

    active: bool = strawberry.field()
    created_at: datetime = strawberry.field()
    updated_at: datetime = strawberry.field()

    @strawberry.field
    async def items(
        self,
        info: Info,
        first: int = 100,
        after: str | None = None,
    ) -> EntityListItemsConnection:
        resolver = info.context["entity_list_items_resolver"]
        return await resolver(
            root=self,
            info=info,
            first=first,
            after=after,
            entity_list_id=self.id,
        )


def entity_list_from_record(
    project_name: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> EntityListNode:
    return EntityListNode(
        project_name=project_name,
        id=record["id"],
        label=record["label"],
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


EntityListNode.from_record = entity_list_from_record  # type: ignore
