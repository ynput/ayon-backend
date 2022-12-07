from typing import TYPE_CHECKING, Any, Literal

import strawberry

from openpype.entities import FolderEntity, UserEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.resolvers.subsets import get_subsets
from openpype.graphql.resolvers.tasks import get_tasks

if TYPE_CHECKING:
    from openpype.graphql.connections import SubsetsConnection, TasksConnection


@FolderEntity.strawberry_attrib()
class FolderAttribType:
    pass


@strawberry.type
class FolderNode(BaseNode):
    folder_type: str | None
    parent_id: str | None
    thumbnail_id: str | None
    path: str | None
    status: str
    tags: list[str]
    attrib: FolderAttribType
    own_attrib: list[str]

    # GraphQL specifics

    child_count: int = strawberry.field(default=0)
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
        return bool(self.child_count)

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


def parse_folder_attrib_data(
    own_attrib: dict[str, Any] | None,
    inherited_attrib: dict[str, Any] | None,
    project_attrib: dict[str, Any] | None,
    user: UserEntity,
    project_name: str | None = None,
) -> FolderAttribType:

    attr_limit: list[str] | Literal["all"] = []

    if user.is_manager:
        attr_limit = "all"
    elif (perms := user.permissions(project_name)) is None:
        attr_limit = []  # This shouldn't happen
    elif perms.attrib_read.enabled:
        attr_limit = perms.attrib_read.attributes

    data = project_attrib or {}
    if inherited_attrib is not None:
        data.update(inherited_attrib)
    if own_attrib is not None:
        data.update(own_attrib)

    if not data:
        return FolderAttribType()
    expected_keys = list(FolderAttribType.__dataclass_fields__.keys())
    for key in expected_keys:  # type: ignore
        if key in data:
            if attr_limit == "all" or key in attr_limit:
                continue
            del data[key]
    return FolderAttribType(**{k: data[k] for k in expected_keys if k in data})


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
        status=record["status"],
        tags=record["tags"],
        attrib=parse_folder_attrib_data(
            record["attrib"],
            record["inherited_attributes"],
            record["project_attributes"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        child_count=record.get("child_count", 0),
        subset_count=record.get("subset_count", 0),
        task_count=record.get("task_count", 0),
        path=record.get("path"),
        own_attrib=list(record["attrib"].keys()),
    )


setattr(FolderNode, "from_record", staticmethod(folder_from_record))
