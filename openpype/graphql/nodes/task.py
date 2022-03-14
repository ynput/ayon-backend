import strawberry
from strawberry.types import Info

from openpype.entities import TaskEntity
from openpype.utils import EntityID

from ..utils import lazy_type, parse_attrib_data
from .common import BaseNode

FolderNode = lazy_type("FolderNode", ".nodes.folder")


@TaskEntity.strawberry_attrib()
class TaskAttribType:
    pass


@TaskEntity.strawberry_entity()
class TaskNode(BaseNode):
    @strawberry.field(description="Parent folder of the task")
    async def folder(self, info: Info) -> FolderNode:
        return await info.context["folder_loader"].load(
            (self.project_name, self.folder_id)
        )


def task_from_record(project_name: str, record: dict, context: dict) -> TaskNode:
    """Construct a task node from a DB row."""
    return TaskNode(
        project_name=project_name,
        id=EntityID.parse(record["id"]),
        name=record["name"],
        task_type=record["task_type"],
        assignees=record["assignees"],
        folder_id=EntityID.parse(record["folder_id"]),
        attrib=parse_attrib_data(
            TaskAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(TaskNode, "from_record", staticmethod(task_from_record))
