import os
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import WorkfileEntity
from ayon_server.graphql.nodes.common import BaseNode
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
    created_by: str | None
    updated_by: str | None
    status: str
    attrib: WorkfileAttribType
    data: str | None
    tags: list[str]

    @strawberry.field(description="Parent task of the workfile")
    async def task(self, info: Info) -> TaskNode:
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return info.context["task_from_record"](self.project_name, record, info.context)


#
# Entity loader
#


def workfile_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> WorkfileNode:
    """Construct a version node from a DB row."""

    data = record.get("data", {})
    name = os.path.basename(record["path"])

    return WorkfileNode(  # type: ignore
        project_name=project_name,
        id=record["id"],
        name=name,
        path=record["path"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        created_by=record["created_by"],
        updated_by=record["updated_by"],
        active=record["active"],
        status=record["status"],
        tags=record["tags"],
        attrib=parse_attrib_data(
            WorkfileAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        data=json_dumps(data) if data else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


WorkfileNode.from_record = staticmethod(workfile_from_record)  # type: ignore
