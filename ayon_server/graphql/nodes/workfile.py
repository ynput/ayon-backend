import os
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import WorkfileEntity
from ayon_server.entities.user import UserEntity
from ayon_server.graphql.nodes.common import BaseNode, ThumbnailInfo
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data
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
    path: str
    task_id: str | None
    thumbnail_id: str | None
    thumbnail: ThumbnailInfo | None = None
    created_by: str | None
    updated_by: str | None
    status: str
    data: str | None
    tags: list[str]

    _attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]

    @strawberry.field(description="Parent task of the workfile")
    async def task(self, info: Info) -> TaskNode:
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return info.context["task_from_record"](self.project_name, record, info.context)

    @strawberry.field
    def attrib(self) -> WorkfileAttribType:
        return parse_attrib_data(
            WorkfileAttribType,
            self._attrib,
            user=self._user,
            project_name=self.project_name,
        )

    @strawberry.field
    def all_attrib(self) -> str:
        return json_dumps(self._attrib)


#
# Entity loader
#


def workfile_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> WorkfileNode:
    """Construct a version node from a DB row."""

    data = record.get("data") or {}
    name = os.path.basename(record["path"])

    thumbnail = None
    if record["thumbnail_id"]:
        thumb_data = data.get("thumbnailInfo", {})
        thumbnail = ThumbnailInfo(
            id=record["thumbnail_id"],
            source_entity_type=thumb_data.get("sourceEntityType"),
            source_entity_id=thumb_data.get("sourceEntityId"),
            relation=thumb_data.get("relation"),
        )

    return WorkfileNode(
        project_name=project_name,
        id=record["id"],
        name=name,
        path=record["path"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        thumbnail=thumbnail,
        created_by=record["created_by"],
        updated_by=record["updated_by"],
        active=record["active"],
        status=record["status"],
        tags=record["tags"],
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        _attrib=record["attrib"] or {},
        _user=context["user"],
    )


WorkfileNode.from_record = staticmethod(workfile_from_record)  # type: ignore
