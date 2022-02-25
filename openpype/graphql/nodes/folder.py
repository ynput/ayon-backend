import strawberry

from openpype.utils import EntityID
from openpype.entities import FolderEntity

from .common import BaseNode
from ..utils import parse_json_data, lazy_type
from ..resolvers.subsets import get_subsets
from ..resolvers.tasks import get_tasks


SubsetsConnection = lazy_type("SubsetsConnection", "..connections")
TasksConnection = lazy_type("TasksConnection", "..connections")


@FolderEntity.strawberry_attrib()
class FolderAttribType:
    pass


@FolderEntity.strawberry_entity()
class FolderNode(BaseNode):
    path: str | None = None
    children_count: int = 0
    subset_count: int = 0
    task_count: int = 0

    subsets: SubsetsConnection = strawberry.field(
        resolver=get_subsets,
        description=get_subsets.__doc__
    )

    tasks: TasksConnection = strawberry.field(
        resolver=get_tasks,
        description=get_tasks.__doc__
    )

    @strawberry.field
    def has_children(self) -> bool:
        return bool(self.children_count)

    @strawberry.field
    def has_subsets(self) -> bool:
        return bool(self.subset_count)

    @strawberry.field
    def has_tasks(self) -> bool:
        return bool(self.task_count)

    @strawberry.field()
    def parents(self) -> list[str]:
        return self.path.split("/")[:-1] if self.path else None


def folder_from_record(
    project_name: str,
    record: dict,
    context: dict | None = None
) -> FolderNode:
    """Construct a folder node from a DB row."""
    return FolderNode(
        project_name=project_name,
        id=EntityID.parse(record["id"]),
        name=record["name"],
        active=record["active"],
        folder_type=record["folder_type"],
        parent_id=EntityID.parse(record["parent_id"], allow_nulls=True),
        attrib=parse_json_data(FolderAttribType, record["attrib"]),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        children_count=record.get("children_count", 0),
        subset_count=record.get("subset_count", 0),
        task_count=record.get("task_count", 0),
        path=record.get("path", None),
    )


setattr(FolderNode, "from_record", staticmethod(folder_from_record))
