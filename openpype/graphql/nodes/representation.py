import enum
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry.types import Info

from openpype.entities import RepresentationEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.utils import lazy_type, parse_attrib_data
from openpype.utils import json_dumps

if TYPE_CHECKING:
    from openpype.graphql.nodes.version import VersionNode
else:
    VersionNode = lazy_type("VersionNode", ".nodes.version")


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
    path: str
    hash: str
    size: int
    local_status: SyncStatusType | None
    remote_status: SyncStatusType | None

    @strawberry.field
    def base_name(self) -> str:
        return self.path.split("/")[-1]


@RepresentationEntity.strawberry_attrib()
class RepresentationAttribType:
    pass


@strawberry.type
class RepresentationNode(BaseNode):
    version_id: str
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

    local_status: SyncStatusType | None = strawberry.field(
        default=None,
        description="Sync status of the representation on the local site",
    )

    remote_status: SyncStatusType | None = strawberry.field(
        default=None,
        description="Sync status of the representation on the remote site",
    )

    context: str | None = strawberry.field(
        default=None,
        description="JSON serialized context data",
    )


def parse_files(
    files: dict,
    local_files: dict[str, Any],
    remote_files: dict[str, Any],
) -> list[FileNode]:
    """Parse the files from a representation."""
    result = []

    if type(files) is not dict:
        return result

    for fid, fdata in files.items():
        file_size = fdata.get("size")
        local_file = local_files.get(fid)
        remote_file = remote_files.get(fid)

        if local_file:
            local_status = SyncStatusType(**local_file, total_size=file_size)
        else:
            local_status = SyncStatusType(status=StatusEnum.NOT_AVAILABLE)

        if remote_file:
            remote_status = SyncStatusType(**remote_file, total_size=file_size)
        else:
            remote_status = SyncStatusType(status=StatusEnum.NOT_AVAILABLE)

        result.append(
            FileNode(
                id=fid,
                path=fdata.get("path"),
                size=fdata.get("size"),
                hash=fdata.get("hash"),
                local_status=local_status,
                remote_status=remote_status,
            )
        )
    return result


def get_overal_status(status, files, site_files):
    size = 0
    total_size = 0
    timestamp = 0
    if type(files) is not dict:
        return SyncStatusType(status=StatusEnum.NOT_AVAILABLE)

    for f in files.values():
        total_size += f["size"]
    for f in site_files.values():
        size += f["size"]
        timestamp = max(timestamp, f["timestamp"])

    return SyncStatusType(
        status=status if status is not None else StatusEnum.NOT_AVAILABLE,
        size=size,
        total_size=total_size,
        timestamp=timestamp
        # message ?
        # retries ?
    )


def representation_from_record(
    project_name: str, record: dict, context: dict
) -> RepresentationNode:  # noqa # no. this line won't be shorter
    """Construct a representation node from a DB row."""

    data = record.get("data") or {}
    files = data.get("files", {})

    local_data: dict[str, Any] = {}
    remote_data: dict[str, Any] = {}
    local_files = {}
    remote_files = {}

    if "local_data" in record:
        local_data = record["local_data"] or {}
        local_files = local_data.get("files", {})

    if "remote_data" in record:
        remote_data = record["remote_data"] or {}
        remote_files = remote_data.get("files", {})

    return RepresentationNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        version_id=record["version_id"],
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
        files=parse_files(files, local_files, remote_files),
        local_status=get_overal_status(record.get("local_status"), files, local_files),
        remote_status=get_overal_status(
            record.get("remote_status"), files, remote_files
        ),
    )


setattr(RepresentationNode, "from_record", staticmethod(representation_from_record))
