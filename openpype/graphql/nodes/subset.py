import strawberry

from strawberry.types import Info
from typing import Optional

from openpype.utils import EntityID
from openpype.entities import SubsetEntity

from .common import BaseNode
from ..resolvers.versions import get_versions
from ..utils import lazy_type, parse_json_data


VersionsConnection = lazy_type("VersionsConnection", ".connections")
FolderNode = lazy_type("FolderNode", ".nodes.folder")
VersionNode = lazy_type("VersionNode", ".nodes.version")


@strawberry.type
class VersionListItem:
    id: str
    version: int


@SubsetEntity.strawberry_attrib()
class SubsetAttribType:
    pass


@SubsetEntity.strawberry_entity()
class SubsetNode(BaseNode):
    versions: VersionsConnection = strawberry.field(
        resolver=get_versions,
        description=get_versions.__doc__
    )

    version_list: list[VersionListItem] = strawberry.field(
        default_factory=list,
        description="Simple (id /version) list of versions in the subset"
    )

    _folder: Optional[FolderNode] = None

    @strawberry.field(description="Parent folder of the subset")
    async def folder(self, info: Info) -> FolderNode:
        # Skip dataloader if already loaded by the subset resolver
        if self._folder:
            return self._folder
        return await info.context["folder_loader"].load(
            (self.project_name, self.folder_id)
        )

    @strawberry.field(description="Last version of the subset")
    async def latest_version(self, info: Info) -> Optional[VersionNode]:
        return await info.context["latest_version_loader"].load(
            (self.project_name, self.id)
        )


def subset_from_record(
    project_name: str,
    record: dict,
    context: dict | None = None
) -> SubsetNode:
    """Construct a subset node from a DB row."""

    if context:
        folder_data = {}
        for key, value in record.items():
            if key.startswith("_folder_"):
                key = key.removeprefix("_folder_")
                folder_data[key] = value

        folder = context["folder_from_record"](project_name, folder_data) \
            if folder_data else None
    else:
        folder = None

    vlist = []
    for id, vers in zip(
        record.get("version_ids", []),
        record.get("version_list", [])
    ):
        vlist.append(
            VersionListItem(id=EntityID.parse(id), version=vers)
        )

    return SubsetNode(
        project_name=project_name,
        id=EntityID.parse(record["id"]),
        name=record["name"],
        folder_id=EntityID.parse(record["folder_id"]),
        family=record["family"],
        attrib=parse_json_data(SubsetAttribType, record["attrib"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        version_list=vlist,
        _folder=folder
    )


setattr(SubsetNode, "from_record", staticmethod(subset_from_record))
