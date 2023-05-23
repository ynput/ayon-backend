import enum
from typing import TYPE_CHECKING, Any

import strawberry
from nxtools import get_base_name
from strawberry import LazyType
from strawberry.types import Info

from ayon_server.entities import RepresentationEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.utils import parse_attrib_data
from ayon_server.utils import json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.nodes.version import VersionNode
else:
    VersionNode = LazyType["VersionNode", ".version"]


class StatusEnum(enum.IntEnum):
    NOT_AVAILABLE = -1
    IN_PROGRESS = 0
    QUEUED = 1
    FAILED = 2
    PAUSED = 3
    SYNCED = 4


@strawberry.type
class SyncStatusType:
    status: int
    size: int = 0
    total_size: int = 0
    timestamp: int = 0
    message: str = ""
    retries: int = 0


@strawberry.type
class FileNode:
    id: str
    name: str
    path: str
    hash: str | None = None
    size: int = 0
    hash_type: str = "md5"


@RepresentationEntity.strawberry_attrib()
class RepresentationAttribType:
    pass


@strawberry.type
class RepresentationNode(BaseNode):
    version_id: str
    status: str
    tags: list[str]
    attrib: RepresentationAttribType

    # GraphQL specifics

    @strawberry.field(description="Parent version of the representation")
    async def version(self, info: Info) -> VersionNode:
        record = await info.context["version_loader"].load(
            (self.project_name, self.version_id)
        )
        return info.context["version_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Number of files of the representation")
    def file_count(self) -> int:
        return len(self.files)

    files: list[FileNode] = strawberry.field(
        description="Files in the representation",
    )

    context: str | None = strawberry.field(
        default=None,
        description="JSON serialized context data",
    )


def parse_files(
    files: list[dict[str, Any]],
) -> list[FileNode]:
    """Parse the files from a representation."""
    result: list[FileNode] = []

    for fdata in files:
        if "name" not in fdata:
            fdata["name"] = get_base_name(fdata["path"])
        result.append(FileNode(**fdata))
    return result


def representation_from_record(
    project_name: str, record: dict, context: dict
) -> RepresentationNode:  # noqa # no. this line won't be shorter
    """Construct a representation node from a DB row."""

    data = record.get("data") or {}

    return RepresentationNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        version_id=record["version_id"],
        status=record["status"],
        tags=record["tags"],
        attrib=parse_attrib_data(
            RepresentationAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        context=json_dumps(data.get("context", {})),
        files=parse_files(record.get("files", [])),
    )


RepresentationNode.from_record = staticmethod(representation_from_record)  # type: ignore
