from typing import TYPE_CHECKING

import strawberry

from openpype.entities import FolderEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.resolvers.subsets import get_subsets
from openpype.graphql.resolvers.tasks import get_tasks
from openpype.graphql.utils import parse_attrib_data

if TYPE_CHECKING:
    from openpype.graphql.connections import SubsetsConnection, TasksConnection


@FolderEntity.strawberry_attrib()
class FolderAttribType:
    pass


@strawberry.type
class FolderNode(BaseNode):
    folder_type: str | None
    parent_id: str
    thumbnail_id: str | None
    path: str
    attrib: FolderAttribType

    # GraphQL specifics

    children_count: int = strawberry.field(default=0)
    subset_count: int = strawberry.field(default=0)
    task_count: int = strawberry.field(default=0)

    subsets: "SubsetsConnection" = strawberry.field(
        resolver=get_subsets,
        description=get_subsets.__doc__,
    )

    tasks: "TasksConnection" = strawberry.field(
        resolver=get_tasks,
        description=get_tasks.__doc__,
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
        return self.path.split("/")[:-1] if self.path else []


#
# Entity loader
#


def folder_from_record(project_name: str, record: dict, context: dict) -> FolderNode:
    """Construct a folder node from a DB row."""
    return FolderNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        active=record["active"],
        folder_type=record["folder_type"],
        parent_id=record["parent_id"],
        thumbnail_id=record["thumbnail_id"],
        attrib=parse_attrib_data(
            FolderAttribType,
            record["attrib"],
            context["user"],
            project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        children_count=record.get("children_count", 0),
        subset_count=record.get("subset_count", 0),
        task_count=record.get("task_count", 0),
        path=record.get("path", None),
    )


setattr(FolderNode, "from_record", staticmethod(folder_from_record))
