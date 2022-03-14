import strawberry
from strawberry.types import Info

from openpype.entities import VersionEntity
from openpype.utils import EntityID

from ..resolvers.representations import get_representations
from ..utils import lazy_type, parse_attrib_data
from .common import BaseNode

SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
RepresentationsConnection = lazy_type("RepresentationsConnection", ".connections")


@VersionEntity.strawberry_attrib()
class VersionAttribType:
    pass


@VersionEntity.strawberry_entity()
class VersionNode(BaseNode):
    representations: RepresentationsConnection = strawberry.field(
        resolver=get_representations, description=get_representations.__doc__
    )

    @strawberry.field(description="Version name")
    def name(self) -> str:
        """Return a version name based on the version number."""
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


def version_from_record(project_name: str, record: dict, context: dict) -> VersionNode:
    """Construct a version node from a DB row."""

    return VersionNode(
        project_name=project_name,
        id=EntityID.parse(record["id"]),
        version=record["version"],
        active=record["active"],
        subset_id=EntityID.parse(record["subset_id"]),
        thumbnail_id=record["thumbnail_id"],
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
