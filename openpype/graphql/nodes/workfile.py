import os
from typing import TYPE_CHECKING

import strawberry
from strawberry.types import Info

from openpype.entities import WorkfileEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.utils import lazy_type, parse_attrib_data

if TYPE_CHECKING:
    from openpype.graphql.nodes.task import TaskNode
else:
    TaskNode = lazy_type("TaskNode", ".nodes.task")


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
    attrib: WorkfileAttribType

    @strawberry.field(description="Workfile name")
    def name(self) -> str:
        """Return a version name based on the workfile path."""
        return os.path.basename(self.path)

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
    project_name: str, record: dict, context: dict
) -> WorkfileNode:
    """Construct a version node from a DB row."""

    return WorkfileNode(  # type: ignore
        project_name=project_name,
        id=record["id"],
        path=record["path"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        created_by=record["created_by"],
        updated_by=record["updated_by"],
        active=record["active"],
        attrib=parse_attrib_data(
            WorkfileAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(WorkfileNode, "from_record", staticmethod(workfile_from_record))
