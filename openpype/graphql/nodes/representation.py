import strawberry
from strawberry.types import Info

from openpype.entities import RepresentationEntity
from openpype.utils import EntityID, json_dumps, json_loads

from ..utils import lazy_type, parse_json_data
from .common import BaseNode

VersionNode = lazy_type("VersionNode", ".nodes.version")
SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
FolderNode = lazy_type("FolderNode", ".nodes.folder")


@strawberry.type
class SyncStateType:
    status: str = "offline"
    size: int = 0
    timestamp: int = 0
    message: str = ""
    retries: int = 0


@strawberry.type
class FileNode:
    id: str
    path: str
    hash: str
    size: int
    local_state: SyncStateType | None
    remote_state: SyncStateType | None

    @strawberry.field
    def base_name(self) -> str:
        return self.path.split("/")[-1]


@RepresentationEntity.strawberry_attrib()
class RepresentationAttribType:
    pass


@RepresentationEntity.strawberry_entity()
class RepresentationNode(BaseNode):
    @strawberry.field(description="Parent version of the representation")
    async def version(self, info: Info) -> VersionNode:
        return await info.context["version_loader"].load(
            (self.project_name, self.version_id)
        )

    @strawberry.field(description="Number of files of the representation")
    def file_count(self) -> int:
        return len(self.files)

    files: list[FileNode] = strawberry.field(
        description="Files in the representation",
    )

    local_state: SyncStateType | None = strawberry.field(
        default=None, description="Sync state of the representation on the local site"
    )

    remote_state: SyncStateType | None = strawberry.field(
        default=None, description="Sync state of the representation on the remote site"
    )

    context: str | None = strawberry.field(
        default=None, description="JSON serialized context data"
    )


def parse_files(
    data: dict, local_state: dict | None = None, remote_state: dict | None = None
) -> list[FileNode]:
    """Parse the files from a representation."""
    files = []

    local_files = local_state.get("files", {})
    remote_files = remote_state.get("files", {})

    for fid, fdata in data.items():
        local_file = local_files.get(fid)
        remote_file = remote_files.get(fid)
        files.append(
            FileNode(
                id=fid,
                path=fdata.get("path"),
                size=fdata.get("size"),
                hash=fdata.get("hash"),
                local_state=SyncStateType(**local_file) if local_file else None,
                remote_state=SyncStateType(**remote_file) if remote_file else None,
            )
        )
    return files


def compute_overal_state(data: dict, state: dict):
    total_size = 0
    transferred = 0
    last_time = 0
    states = []
    for _, fdata in data.get("files", {}).items():
        total_size += fdata.get("size")

    for _, fdata in state.get("files", {}).items():
        transferred += fdata.get("size")
        last_time = max(last_time, fdata.get("timestamp"))
        states.append(fdata.get("status"))

    if not states:
        return SyncStateType(status="offline")
    elif not transferred:

        return SyncStateType(
            status="pending",
            size=total_size,
        )
    elif transferred == total_size:
        return SyncStateType(
            status="online",
            size=total_size,
            timestamp=last_time,
        )
    else:
        return SyncStateType(
            status="in_progress",
            size=transferred,
            timestamp=last_time,
        )


def representation_from_record(
    project_name: str, record: dict, context: dict | None = None
) -> RepresentationNode:  # noqa # no. this line won't be shorter
    """Construct a representation node from a DB row."""
    data = json_loads(record["data"]) or {}

    local_state = remote_state = {}

    if "local_state" in record:
        local_state = json_loads(record["local_state"] or "{}")

    if "remote_state" in record:
        remote_state = json_loads(record["remote_state"] or "{}")

    return RepresentationNode(
        project_name=project_name,
        id=EntityID.parse(record["id"]),
        name=record["name"],
        version_id=EntityID.parse(record["version_id"]),
        attrib=parse_json_data(RepresentationAttribType, record["attrib"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        local_state=compute_overal_state(data, local_state),
        remote_state=compute_overal_state(data, remote_state),
        context=json_dumps(data.get("context")),
        files=parse_files(data.get("files", {}), local_state, remote_state),
    )


setattr(RepresentationNode, "from_record", staticmethod(representation_from_record))
