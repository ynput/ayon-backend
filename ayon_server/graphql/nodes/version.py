from typing import TYPE_CHECKING, Any, Optional

import strawberry
from strawberry import LazyType

from ayon_server.entities import VersionEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.resolvers.representations import get_representations
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data, parse_data
from ayon_server.utils import get_nickname

if TYPE_CHECKING:
    from ayon_server.graphql.connections import RepresentationsConnection
    from ayon_server.graphql.nodes.product import ProductNode
    from ayon_server.graphql.nodes.task import TaskNode
else:
    RepresentationsConnection = LazyType["RepresentationsConnection", "..connections"]
    ProductNode = LazyType["ProductNode", ".product"]
    TaskNode = LazyType["TaskNode", ".task"]


@VersionEntity.strawberry_attrib()
class VersionAttribType:
    pass


@strawberry.type
class VersionNode(BaseNode):
    version: int
    product_id: str
    task_id: str | None
    thumbnail_id: str | None
    author: str | None
    status: str
    attrib: VersionAttribType
    data: str | None
    tags: list[str]

    # GraphQL specifics

    representations: "RepresentationsConnection" = strawberry.field(
        resolver=get_representations,
        description=get_representations.__doc__,
    )

    @strawberry.field(description="Parent product of the version")
    async def product(self, info: Info) -> ProductNode:
        record = await info.context["product_loader"].load(
            (self.project_name, self.product_id)
        )
        return info.context["product_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Task")
    async def task(self, info: Info) -> Optional[TaskNode]:
        if self.task_id is None:
            return None
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return info.context["task_from_record"](self.project_name, record, info.context)


#
# Entity loader
#


def version_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> VersionNode:
    """Construct a version node from a DB row."""

    current_user = context["user"]
    author = record["author"]
    if current_user.is_guest and author is not None:
        author = get_nickname(author)

    data = record.get("data", {})
    version_no = record["version"]
    if version_no < 0:
        name = "HERO"
    else:
        name = f"v{record['version']:03d}"

    return VersionNode(
        project_name=project_name,
        id=record["id"],
        name=name,
        version=record["version"],
        active=record["active"],
        product_id=record["product_id"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        author=author,
        status=record["status"],
        tags=record["tags"],
        attrib=parse_attrib_data(
            VersionAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        data=parse_data(data),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


VersionNode.from_record = staticmethod(version_from_record)  # type: ignore
