from datetime import datetime
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import ProductEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.resolvers.versions import get_versions
from ayon_server.graphql.types import Info
from ayon_server.utils import json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.connections import VersionsConnection
    from ayon_server.graphql.nodes.folder import FolderNode
    from ayon_server.graphql.nodes.version import VersionNode
else:
    FolderNode = LazyType["FolderNode", ".folder"]
    VersionNode = LazyType["VersionNode", ".version"]
    VersionsConnection = LazyType["VersionsConnection", "..connections"]


@strawberry.type
class VersionListItem:
    id: str
    version: int

    @strawberry.field(description="Version name")
    def name(self) -> str:
        """Return a version name based on the version number."""
        if self.version < 0:
            return "HERO"
        # TODO: configurable zero pad / format?
        return f"v{self.version:03d}"


@ProductEntity.strawberry_attrib()
class ProductAttribType:
    pass


@strawberry.type
class ProductNode(BaseNode):
    entity_type: strawberry.Private[str] = "product"
    folder_id: str
    product_type: str
    product_base_type: str | None
    status: str
    tags: list[str]
    data: str | None
    path: str | None = None

    _folder_path: strawberry.Private[str | None] = None

    _hero_version_data: strawberry.Private[dict[str, Any] | None] = None
    _latest_done_version_data: strawberry.Private[dict[str, Any] | None] = None
    _latest_version_data: strawberry.Private[dict[str, Any] | None] = None

    # GraphQL specifics

    @strawberry.field
    def type(self) -> str:
        """Alias for `productType`"""
        return self.product_type

    versions: VersionsConnection = strawberry.field(
        resolver=get_versions,
        description=get_versions.__doc__,
    )

    version_list: list[VersionListItem] = strawberry.field(
        default_factory=list,
        description="Simple (id /version) list of versions in the product",
    )

    _folder: FolderNode | None = None

    @strawberry.field(description="Parent folder of the product")
    async def folder(self, info: Info) -> FolderNode:
        # Skip dataloader if already loaded by the product resolver
        if self._folder:
            return self._folder
        record = await info.context["folder_loader"].load(
            (self.project_name, self.folder_id)
        )
        return await info.context["folder_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Last version of the product")
    async def latest_version(self, info: Info) -> VersionNode | None:
        record = await info.context["latest_version_loader"].load(
            (self.project_name, self.id)
        )
        if record is None:
            return None

        return await info.context["version_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field
    def attrib(self) -> ProductAttribType:
        return ProductAttribType(**self.processed_attrib())

    @strawberry.field()
    def parents(self) -> list[str]:
        if not self.path:
            return []
        path = self.path.strip("/")
        return path.split("/")[:-1] if path else []

    @strawberry.field
    async def featured_version(
        self,
        info: Info,
        order: list[str] | None = None,
    ) -> VersionNode | None:
        """Return the featured version of the product.

        Order may contain ["latestDone", "hero", "latest"]
        which is the order of preference for the featured version.

        This array is optional, if not provided, this exact order is used.

        This node may be null if no versions are available.
        """

        if order is None:
            order = ["latestDone", "hero", "latest"]

        for item in order:
            if item == "hero" and self._hero_version_data:
                data = self._hero_version_data
                data["featured_version_type"] = "hero"
            elif item == "latestDone" and self._latest_done_version_data:
                data = self._latest_done_version_data
                data["featured_version_type"] = "latestDone"
            elif item == "latest" and self._latest_version_data:
                data = self._latest_version_data
                data["featured_version_type"] = "latest"
            else:
                continue

            data["_folder_path"] = self._folder_path
            data["_product_name"] = self.name
            data["id"] = data["id"].replace("-", "")
            data["hero_version_id"] = (
                data["hero_version_id"].replace("-", "")
                if data.get("hero_version_id")
                else None
            )
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

            return await info.context["version_from_record"](
                self.project_name, data, info.context
            )

        return None


async def product_from_record(
    project_name: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> ProductNode:
    """Construct a product node from a DB row."""

    folder = None
    if context:
        folder_data = {}
        for key, value in record.items():
            if key.startswith("_folder_"):
                key = key.removeprefix("_folder_")
                folder_data[key] = value

        if folder_data.get("id"):
            try:
                cfun = context["folder_from_record"]
                if folder_data is None:
                    folder = None
                else:
                    folder = await cfun(project_name, folder_data, context=context)
            except KeyError:
                pass

    vlist = []
    version_ids = record.get("version_ids", [])
    version_list = record.get("version_list", [])
    if version_ids and version_list:
        for id, vers in zip(version_ids, version_list):
            vlist.append(VersionListItem(id=id, version=vers))

    data = record.get("data", {})

    path = None
    folder_path = None
    if record.get("_folder_path"):
        folder_path = "/" + record["_folder_path"].strip("/")
        path = f"{folder_path}/{record['name']}"

    return ProductNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        folder_id=record["folder_id"],
        product_type=record["product_type"],
        product_base_type=record.get("product_base_type"),
        status=record["status"],
        tags=record["tags"],
        data=json_dumps(data) if data else None,
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        created_by=record.get("created_by"),
        updated_by=record.get("updated_by"),
        version_list=vlist,
        path=path,
        _folder=folder,
        _folder_path=folder_path,
        _attrib=record["attrib"] or {},
        _user=context["user"],
        _hero_version_data=record.get("_hero_version_data"),
        _latest_done_version_data=record.get("_latest_done_version_data"),
        _latest_version_data=record.get("_latest_version_data"),
    )


ProductNode.from_record = staticmethod(product_from_record)  # type: ignore
