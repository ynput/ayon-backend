from typing import TYPE_CHECKING, Annotated, Any

import strawberry

from ayon_server.entities import VersionEntity
from ayon_server.graphql.nodes.common import BaseNode, ThumbnailInfo
from ayon_server.graphql.nodes.entity_comment import EntityComment
from ayon_server.graphql.resolvers.representations import get_representations
from ayon_server.graphql.types import Info
from ayon_server.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from ayon_server.graphql.connections import RepresentationsConnection
    from ayon_server.graphql.nodes.product import ProductNode
    from ayon_server.graphql.nodes.task import TaskNode
else:
    RepresentationsConnection = Annotated[
        "RepresentationsConnection",
        strawberry.lazy("..connections"),
    ]
    ProductNode = Annotated["ProductNode", strawberry.lazy(".product")]
    TaskNode = Annotated["TaskNode", strawberry.lazy(".task")]


@VersionEntity.strawberry_attrib()
class VersionAttribType:
    pass


@strawberry.type
class VersionNode(BaseNode):
    entity_type: strawberry.Private[str] = "version"
    version: int
    product_id: str
    status: str
    tags: list[str]
    task_id: str | None = None
    thumbnail_id: str | None = None
    thumbnail: ThumbnailInfo | None = None
    thumbnail_hash: str = strawberry.field()
    has_reviewables: bool = False
    author: str | None = None
    data: str | None = None
    path: str | None = None
    hero_version_id: str | None = None
    featured_version_type: str | None = None
    is_latest: bool = False
    is_latest_done: bool = False

    latest_comments: list[EntityComment] | None = strawberry.field(default=None)

    _folder_path: strawberry.Private[str | None] = None

    _product: strawberry.Private[ProductNode | None] = None

    # GraphQL specifics

    representations: RepresentationsConnection = strawberry.field(
        resolver=get_representations,
        description=get_representations.__doc__,
    )

    @strawberry.field(description="Parent product of the version")
    async def product(self, info: Info) -> ProductNode:
        if self._product:
            return self._product

        record = await info.context["product_loader"].load(
            (self.project_name, self.product_id)
        )
        product = await info.context["product_from_record"](
            self.project_name, record, info.context
        )

        if product:
            folder_record = await info.context["folder_loader"].load(
                (self.project_name, product.folder_id)
            )
            folder = await info.context["folder_from_record"](
                self.project_name, folder_record, info.context
            )
            product._folder = folder

        return product

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
        return VersionAttribType(**self.processed_attrib())

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

    product = None
    folder = None
    if context:
        product_data = {}
        folder_data = {}
        for key, value in record.items():
            if key.startswith("_product_"):
                key = key.removeprefix("_product_")
                product_data[key] = value

            if key.startswith("_folder_"):
                key = key.removeprefix("_folder_")
                folder_data[key] = value

        if product_data.get("id"):
            try:
                cfun = context["product_from_record"]
                if product_data is None:
                    product = None
                else:
                    product = await cfun(project_name, product_data, context=context)
            except KeyError:
                pass

        if product and folder_data.get("id"):
            try:
                cfun = context["folder_from_record"]
                if folder_data is None:
                    folder = None
                else:
                    folder = await cfun(project_name, folder_data, context=context)
                    product._folder = folder
            except KeyError:
                pass

    current_user = context["user"]
    author = record["author"]

    data = record.get("data") or {}
    thumbnail_hash = data.get("thumbnailHash") or record["id"][-6:]
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
    folder_path = None
    if record.get("_folder_path"):
        folder_path = "/" + record["_folder_path"].strip("/")
        product_name = record["_product_name"]
        path = f"{folder_path}/{product_name}/{name}"

    try:
        latest_comments = json_loads(record.get("latest_comments") or "[]")
    except Exception:
        latest_comments = []

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
        thumbnail_hash=thumbnail_hash,
        has_reviewables=has_reviewables,
        author=author,
        status=record["status"],
        tags=record["tags"],
        path=path,
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        created_by=record.get("created_by"),
        updated_by=record.get("updated_by"),
        hero_version_id=record.get("hero_version_id"),
        featured_version_type=record.get("featured_version_type"),
        is_latest=record.get("is_latest", False),
        is_latest_done=record.get("is_latest_done", False),
        latest_comments=[EntityComment(**comment) for comment in latest_comments],
        _product=product,
        _folder_path=folder_path,
        _attrib=record["attrib"] or {},
        _user=current_user,
    )


VersionNode.from_record = staticmethod(version_from_record)  # type: ignore
