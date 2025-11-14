from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import WorkfileEntity
from ayon_server.graphql.nodes.common import BaseNode, ThumbnailInfo
from ayon_server.graphql.types import Info
from ayon_server.utils import json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.nodes.task import TaskNode
else:
    TaskNode = LazyType["TaskNode", ".task"]


@WorkfileEntity.strawberry_attrib()
class WorkfileAttribType:
    pass


@strawberry.type
class WorkfileNode(BaseNode):
    entity_type: strawberry.Private[str] = "workfile"
    path: str
    task_id: str | None
    thumbnail_id: str | None
    thumbnail: ThumbnailInfo | None = None
    status: str
    data: str | None
    tags: list[str]

    _parents: list[str] | None = None
    _folder_path: strawberry.Private[str | None] = None

    @strawberry.field(description="Parent task of the workfile")
    async def task(self, info: Info) -> TaskNode:
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return await info.context["task_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field
    def attrib(self) -> WorkfileAttribType:
        return WorkfileAttribType(**self.processed_attrib())

    @strawberry.field()
    def parents(self) -> list[str]:
        return self._parents or []


#
# Entity loader
#


async def workfile_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> WorkfileNode:
    """Construct a version node from a DB row."""

    data = record.get("data") or {}
    npath = record["path"].replace("\\", "/")
    name = npath.split("/")[-1] if npath else ""

    thumbnail = None
    if record["thumbnail_id"]:
        thumb_data = data.get("thumbnailInfo", {})
        thumbnail = ThumbnailInfo(
            id=record["thumbnail_id"],
            source_entity_type=thumb_data.get("sourceEntityType"),
            source_entity_id=thumb_data.get("sourceEntityId"),
            relation=thumb_data.get("relation"),
        )

    parents: list[str] = []
    folder_path = None
    if folder_path := record.get("_folder_path"):
        folder_path = "/" + folder_path.strip("/")
        parents = folder_path.split("/")[:-1] if folder_path else []
        parents.append(record["_task_name"])

    return WorkfileNode(
        project_name=project_name,
        id=record["id"],
        name=name,
        path=record["path"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        thumbnail=thumbnail,
        active=record["active"],
        status=record["status"],
        tags=record["tags"],
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        created_by=record.get("created_by"),
        updated_by=record.get("updated_by"),
        _attrib=record["attrib"] or {},
        _user=context["user"],
        _parents=parents,
        _folder_path=folder_path,
    )


WorkfileNode.from_record = staticmethod(workfile_from_record)  # type: ignore
