from typing import TYPE_CHECKING, Any

import strawberry
from strawberry import LazyType

from ayon_server.entities import TaskEntity
from ayon_server.entities.user import UserEntity
from ayon_server.graphql.nodes.common import BaseNode, ThumbnailInfo
from ayon_server.graphql.resolvers.versions import get_versions
from ayon_server.graphql.resolvers.workfiles import get_workfiles
from ayon_server.graphql.types import Info
from ayon_server.graphql.utils import parse_attrib_data
from ayon_server.utils import get_nickname, json_dumps

if TYPE_CHECKING:
    from ayon_server.graphql.connections import VersionsConnection, WorkfilesConnection
    from ayon_server.graphql.nodes.folder import FolderNode
else:
    FolderNode = LazyType["FolderNode", ".folder"]
    VersionsConnection = LazyType["VersionsConnection", "..connections"]
    WorkfilesConnection = LazyType["WorkfilesConnection", "..connections"]


@TaskEntity.strawberry_attrib()
class TaskAttribType:
    pass


@strawberry.type
class TaskNode(BaseNode):
    label: str | None
    task_type: str
    thumbnail_id: str | None = None
    thumbnail: ThumbnailInfo | None = None
    assignees: list[str]
    folder_id: str
    status: str
    has_reviewables: bool
    tags: list[str]
    data: str | None
    path: str | None = None

    _attrib: strawberry.Private[dict[str, Any]]
    _inherited_attrib: strawberry.Private[dict[str, Any]]
    _user: strawberry.Private[UserEntity]

    # GraphQL specifics

    versions: "VersionsConnection" = strawberry.field(
        resolver=get_versions,
        description=get_versions.__doc__,
    )

    workfiles: "WorkfilesConnection" = strawberry.field(
        resolver=get_workfiles,
        description=get_workfiles.__doc__,
    )

    _folder: FolderNode | None = None

    @strawberry.field
    def type(self) -> str:
        """Alias for `taskType`"""
        return self.task_type

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

    @strawberry.field
    def attrib(self) -> TaskAttribType:
        return parse_attrib_data(
            TaskAttribType,
            self._attrib,
            user=self._user,
            project_name=self.project_name,
            inherited_attrib=self._inherited_attrib,
        )

    @strawberry.field
    def all_attrib(self) -> str:
        """Return all attributes (inherited and own) as JSON string."""
        all_attrib = {
            **self._inherited_attrib,
            **self._attrib,
        }
        return json_dumps(all_attrib)

    @strawberry.field
    def own_attrib(self) -> list[str]:
        """Return a list of attributes that are defined on the task."""
        return list(self._attrib.keys())

    @strawberry.field()
    def parents(self) -> list[str]:
        if not self.path:
            return []
        path = self.path.strip("/")
        return path.split("/")[:-1] if path else []


def task_from_record(
    project_name: str, record: dict[str, Any], context: dict[str, Any]
) -> TaskNode:
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

    current_user = context["user"]
    assignees: list[str] = []
    if current_user.is_guest:
        for assignee in record["assignees"]:
            if assignee == current_user.name:
                assignees.append(assignee)
            else:
                assignees.append(get_nickname(assignee))
    else:
        assignees = record["assignees"]

    data = record.get("data") or {}

    if "has_reviewables" in record:
        has_reviewables = record["has_reviewables"]
    else:
        has_reviewables = False

    thumbnail = None
    if record["thumbnail_id"]:
        thumb_data = data.get("thumbnailInfo", {})
        thumbnail = ThumbnailInfo(
            id=record["thumbnail_id"],
            source_entity_type=thumb_data.get("sourceEntityType"),
            source_entity_id=thumb_data.get("sourceEntityId"),
            relation=thumb_data.get("relation"),
        )

    path = None
    if record.get("_folder_path"):
        folder_path = record["_folder_path"].strip("/")
        path = f"/{folder_path}/{record['name']}"

    return TaskNode(
        project_name=project_name,
        id=record["id"],
        name=record["name"],
        label=record["label"],
        task_type=record["task_type"],
        thumbnail_id=record["thumbnail_id"],
        thumbnail=thumbnail,
        assignees=assignees,
        folder_id=record["folder_id"],
        status=record["status"],
        has_reviewables=has_reviewables,
        tags=record["tags"],
        data=json_dumps(data) if data else None,
        active=record["active"],
        path=path,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        _folder=folder,
        _attrib=record["attrib"],
        _inherited_attrib=record["parent_folder_attrib"],
        _user=current_user,
    )


TaskNode.from_record = staticmethod(task_from_record)  # type: ignore
