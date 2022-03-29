from typing import Optional

import strawberry
from strawberry.types import Info

from openpype.entities import TaskEntity

from ..resolvers.versions import get_versions
from ..utils import lazy_type, parse_attrib_data
from .common import BaseNode

FolderNode = lazy_type("FolderNode", ".nodes.folder")
VersionsConnection = lazy_type("VersionsConnection", "..connections")


@TaskEntity.strawberry_attrib()
class TaskAttribType:
    pass


@TaskEntity.strawberry_entity()
class TaskNode(BaseNode):
    versions: VersionsConnection = strawberry.field(
        resolver=get_versions, description=get_versions.__doc__
    )

    _folder: Optional[FolderNode] = None

    @strawberry.field(description="Parent folder of the task")
    async def folder(self, info: Info) -> FolderNode:
        if self._folder:
            return self._folder
        record = await info.context["folder_loader"].load(
            (self.project_name, self.folder_id)
        )
        return info.context["folder_from_record"](
            self.project_name, record, info.context
        )


def task_from_record(project_name: str, record: dict, context: dict) -> TaskNode:
    """Construct a task node from a DB row."""
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

    return TaskNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        task_type=record["task_type"],
        assignees=record["assignees"],
        folder_id=record["folder_id"],
        attrib=parse_attrib_data(
            TaskAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        _folder=folder,
    )


setattr(TaskNode, "from_record", staticmethod(task_from_record))
