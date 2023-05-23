from typing import TYPE_CHECKING, Optional

import strawberry
from strawberry import LazyType
from strawberry.types import Info

from ayon_server.entities import VersionEntity
from ayon_server.graphql.nodes.common import BaseNode
from ayon_server.graphql.resolvers.representations import get_representations
from ayon_server.graphql.utils import parse_attrib_data
from ayon_server.utils import get_nickname

if TYPE_CHECKING:
    from ayon_server.graphql.connections import RepresentationsConnection
    from ayon_server.graphql.nodes.subset import SubsetNode
    from ayon_server.graphql.nodes.task import TaskNode
else:
    RepresentationsConnection = LazyType["RepresentationsConnection", "..connections"]
    SubsetNode = LazyType["SubsetNode", ".subset"]
    TaskNode = LazyType["TaskNode", ".task"]


@VersionEntity.strawberry_attrib()
class VersionAttribType:
    pass


@strawberry.type
class VersionNode(BaseNode):
    version: int
    subset_id: str
    task_id: str | None
    thumbnail_id: str | None
    author: str | None
    status: str
    attrib: VersionAttribType
    tags: list[str]

    # GraphQL specifics

    representations: "RepresentationsConnection" = strawberry.field(
        resolver=get_representations,
        description=get_representations.__doc__,
    )

    @strawberry.field(description="Version name")
    def name(self) -> str:
        """Return a version name based on the version number."""
        if self.version < 0:
            return "HERO"
        # TODO: configurable zero pad / format?
        return f"v{self.version:03d}"

    @strawberry.field(description="Parent subset of the version")
    async def subset(self, info: Info) -> SubsetNode:
        record = await info.context["subset_loader"].load(
            (self.project_name, self.subset_id)
        )
        return info.context["subset_from_record"](
            self.project_name, record, info.context
        )

    @strawberry.field(description="Task")
    async def task(self, info: Info) -> Optional[TaskNode]:
        if self.task_id is None:
            return None
        record = await info.context["task_loader"].load(
            (self.project_name, self.task_id)
        )
        return info.context["task_from_record"](self.project_name, record, info.context)


#
# Entity loader
#


def version_from_record(project_name: str, record: dict, context: dict) -> VersionNode:
    """Construct a version node from a DB row."""

    current_user = context["user"]
    author = record["author"]
    if current_user.is_guest and author is not None:
        author = get_nickname(author)

    return VersionNode(  # type: ignore
        project_name=project_name,
        id=record["id"],
        version=record["version"],
        active=record["active"],
        subset_id=record["subset_id"],
        task_id=record["task_id"],
        thumbnail_id=record["thumbnail_id"],
        author=author,
        status=record["status"],
        tags=record["tags"],
        attrib=parse_attrib_data(
            VersionAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


VersionNode.from_record = staticmethod(version_from_record)  # type: ignore
