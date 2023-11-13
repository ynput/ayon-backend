from typing import TYPE_CHECKING, Optional

import strawberry
from strawberry import LazyType
from strawberry.types import Info

from ayon_server.entities import FolderEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.resolvers.products import get_products
from ayon_server.graphql.resolvers.tasks import get_tasks
from ayon_server.graphql.utils import parse_attrib_data
from ayon_server.utils import json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.connections import ProductsConnection, TasksConnection
else:
    ProductsConnection = LazyType["ProductsConnection", "..connections"]
    TasksConnection = LazyType["TasksConnection", "..connections"]


@FolderEntity.strawberry_attrib()
class FolderAttribType:
    pass


@strawberry.type
class FolderNode(BaseNode):
    label: str | None
    folder_type: str
    parent_id: str | None
    thumbnail_id: str | None
    path: str | None
    status: str
    tags: list[str]
    attrib: FolderAttribType
    own_attrib: list[str]
    data: str | None

    # GraphQL specifics

    child_count: int = strawberry.field(default=0)
    product_count: int = strawberry.field(default=0)
    task_count: int = strawberry.field(default=0)

    products: ProductsConnection = strawberry.field(
        resolver=get_products,
        description=get_products.__doc__,
    )

    tasks: TasksConnection = strawberry.field(
        resolver=get_tasks,
        description=get_tasks.__doc__,
    )

    @strawberry.field
    def type(self) -> str:
        """Alias for `folderType`"""
        return self.folder_type

    @strawberry.field
    def has_children(self) -> bool:
        return bool(self.child_count)

    @strawberry.field
    def has_products(self) -> bool:
        return bool(self.product_count)

    @strawberry.field
    def has_tasks(self) -> bool:
        return bool(self.task_count)

    @strawberry.field()
    def parents(self) -> list[str]:
        return self.path.split("/")[:-1] if self.path else []

    @strawberry.field
    async def parent(self, info: Info) -> Optional["FolderNode"]:
        if not self.parent_id:
            return None
        record = await info.context["folder_loader"].load(
            (self.project_name, self.parent_id)
        )
        return (
            info.context["folder_from_record"](self.project_name, record, info.context)
            if record
            else None
        )


#
# Entity loader
#


def folder_from_record(project_name: str, record: dict, context: dict) -> FolderNode:
    """Construct a folder node from a DB row."""

    own_attrib = list(record["attrib"].keys())
    data = record.get("data")

    return FolderNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        label=record["label"],
        active=record["active"],
        folder_type=record["folder_type"],
        parent_id=record["parent_id"],
        thumbnail_id=record["thumbnail_id"],
        status=record["status"],
        tags=record["tags"],
        attrib=parse_attrib_data(
            FolderAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
            project_attrib=record["project_attributes"],
            inherited_attrib=record["inherited_attributes"],
        ),
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        child_count=record.get("child_count", 0),
        product_count=record.get("product_count", 0),
        task_count=record.get("task_count", 0),
        path=record.get("path"),
        own_attrib=own_attrib,
    )


FolderNode.from_record = staticmethod(folder_from_record)  # type: ignore
