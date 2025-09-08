from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import VersionEntity
from ayon_server.entities.user import UserEntity
from ayon_server.graphql.nodes.common import BaseNode, ThumbnailInfo
from ayon_server.graphql.resolvers.representations import get_representations
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data, process_attrib_data
from ayon_server.utils import json_dumps

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
    status: str
    tags: list[str]
    task_id: str | None = None
    thumbnail_id: str | None = None
    thumbnail: ThumbnailInfo | None = None
    has_reviewables: bool = False
    author: str | None = None
    data: str | None = None
    path: str | None = None

    _attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]

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
        return await info.context["product_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Task")
    async def task(self, info: Info) -> TaskNode | None:
        if self.task_id is None:
            return None
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return await info.context["task_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field
    def attrib(self) -> VersionAttribType:
        return parse_attrib_data(
            VersionAttribType,
            self._attrib,
            user=self._user,
            project_name=self.project_name,
        )

    @strawberry.field
    def all_attrib(self) -> str:
        return json_dumps(
            process_attrib_data(
                self._attrib,
                user=self._user,
                project_name=self.project_name,
            )
        )

    @strawberry.field()
    def parents(self) -> list[str]:
        if not self.path:
            return []
        path = self.path.strip("/")
        return path.split("/")[:-1] if path else []


#
# Entity loader
#


async def version_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> VersionNode:
    """Construct a version node from a DB row."""

    current_user = context["user"]
    author = record["author"]

    data = record.get("data") or {}
    version_no = record["version"]
    if version_no < 0:
        name = "HERO"
    else:
        name = f"v{record['version']:03d}"

    if "has_reviewables" in record:
        has_reviewables = record["has_reviewables"]
    else:
        has_reviewables = False

    thumbnail = None
    if record["thumbnail_id"]:
        thumb_data = data.get("thumbnailInfo", {})
        thumbnail = ThumbnailInfo(
            id=record["thumbnail_id"],
            source_entity_type=thumb_data.get("sourceEntityType"),
            source_entity_id=thumb_data.get("sourceEntityId"),
            relation=thumb_data.get("relation"),
        )

    path = None
    if record.get("_folder_path"):
        folder_path = record["_folder_path"].strip("/")
        product_name = record["_product_name"]
        path = f"/{folder_path}/{product_name}/{name}"

    return VersionNode(
        project_name=project_name,
        id=record["id"],
        name=name,
        version=record["version"],
        active=record["active"],
        product_id=record["product_id"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        thumbnail=thumbnail,
        has_reviewables=has_reviewables,
        author=author,
        status=record["status"],
        tags=record["tags"],
        path=path,
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        _attrib=record["attrib"] or {},
        _user=current_user,
    )


VersionNode.from_record = staticmethod(version_from_record)  # type: ignore
