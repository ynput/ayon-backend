from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import ProductEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.resolvers.versions import get_versions
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data
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
    folder_id: str
    product_type: str
    product_base_type: str | None
    status: str
    tags: list[str]
    attrib: ProductAttribType
    all_attrib: str
    data: str | None

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
        return info.context["folder_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Last version of the product")
    async def latest_version(self, info: Info) -> VersionNode | None:
        record = await info.context["latest_version_loader"].load(
            (self.project_name, self.id)
        )
        return (
            info.context["version_from_record"](self.project_name, record, info.context)
            if record
            else None
        )


def product_from_record(
    project_name: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> ProductNode:
    """Construct a product node from a DB row."""

    if context:
        folder_data = {}
        for key, value in record.items():
            if key.startswith("_folder_"):
                key = key.removeprefix("_folder_")
                folder_data[key] = value

        folder = (
            context["folder_from_record"](project_name, folder_data, context=context)
            if folder_data
            else None
        )
    else:
        folder = None

    vlist = []
    version_ids = record.get("version_ids", [])
    version_list = record.get("version_list", [])
    if version_ids and version_list:
        for id, vers in zip(version_ids, version_list):
            vlist.append(VersionListItem(id=id, version=vers))

    data = record.get("data", {})
    attrib = parse_attrib_data(
        ProductAttribType,
        record["attrib"],
        user=context["user"],
        project_name=project_name,
    )

    return ProductNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        folder_id=record["folder_id"],
        product_type=record["product_type"],
        product_base_type=record.get("product_base_type"),
        status=record["status"],
        tags=record["tags"],
        attrib=ProductAttribType(**attrib),
        data=json_dumps(data) if data else None,
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        version_list=vlist,
        all_attrib=json_dumps(attrib),
        _folder=folder,
    )


ProductNode.from_record = staticmethod(product_from_record)  # type: ignore
