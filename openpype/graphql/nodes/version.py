from typing import TYPE_CHECKING, Optional

import strawberry
from strawberry.types import Info

from openpype.entities import VersionEntity
from openpype.graphql.nodes.common import BaseNode
from openpype.graphql.resolvers.representations import get_representations
from openpype.graphql.utils import lazy_type, parse_attrib_data

if TYPE_CHECKING:
    from openpype.graphql.connections import RepresentationsConnection


SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
TaskNode = lazy_type("TaskNode", ".nodes.task")


@VersionEntity.strawberry_attrib()
class VersionAttribType:
    pass


@strawberry.type
class VersionNode(BaseNode):
    version: int
    subset_id: str
    task_id: str | None
    author: str
    attrib: VersionAttribType

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

    return VersionNode(  # type: ignore
        project_name=project_name,
        id=record["id"],
        version=record["version"],
        active=record["active"],
        subset_id=record["subset_id"],
        task_id=record["task_id"],
        author=record["author"],
        attrib=parse_attrib_data(
            VersionAttribType,
            record["attrib"],
            user=context["user"],
            project_name=project_name,
        ),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


setattr(VersionNode, "from_record", staticmethod(version_from_record))
