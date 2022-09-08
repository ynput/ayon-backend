from typing import TYPE_CHECKING, Any, Literal, Optional

import strawberry
from strawberry.types import Info

from openpype.entities import TaskEntity, UserEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.resolvers.versions import get_versions
from openpype.graphql.utils import lazy_type

if TYPE_CHECKING:
    from openpype.graphql.connections import VersionsConnection
    from openpype.graphql.nodes.folder import FolderNode
else:
    FolderNode = lazy_type("FolderNode", ".nodes.folder")


@TaskEntity.strawberry_attrib()
class TaskAttribType:
    pass


@strawberry.type
class TaskNode(BaseNode):
    task_type: str
    assignees: list[str]
    folder_id: str
    attrib: TaskAttribType
    own_attrib: list[str]

    # GraphQL specifics

    versions: "VersionsConnection" = strawberry.field(
        resolver=get_versions,
        description=get_versions.__doc__,
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


def parse_task_attrib_data(
    task_attrib: dict[str, Any] | None,
    parent_folder_attrib: dict[str, Any] | None,
    user: UserEntity,
    project_name: str | None = None,
) -> TaskAttribType:

    attr_limit: list[str] | Literal["all"] = []

    if user.is_manager:
        attr_limit = "all"
    elif (perms := user.permissions(project_name)) is None:
        attr_limit = []  # This shouldn't happen
    elif perms.attrib_read.enabled:
        attr_limit = perms.attrib_read.attributes

    data: dict[str, Any] = {}
    if parent_folder_attrib is not None:
        data |= parent_folder_attrib
    if task_attrib is not None:
        data |= task_attrib

    if not data:
        return TaskAttribType()
    valid_keys = list(TaskAttribType.__dataclass_fields__.keys())  # type: ignore
    for key in valid_keys:
        if key in data:
            if attr_limit == "all" or key in attr_limit:
                continue
            del data[key]
    return TaskAttribType(**{k: v for k, v in data.items() if k in valid_keys})


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
        attrib=parse_task_attrib_data(
            record["attrib"],
            record["parent_folder_attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        active=record["active"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        own_attrib=list(record["attrib"].keys()),
        _folder=folder,
    )


setattr(TaskNode, "from_record", staticmethod(task_from_record))
