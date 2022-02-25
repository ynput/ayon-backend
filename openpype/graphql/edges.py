import strawberry

from .utils import lazy_type

# Use lazy typing to prevent circular imports
# We don't need actual types here, just the names

ProjectNode = lazy_type("ProjectNode", ".nodes.project")
UserNode = lazy_type("UserNode", ".nodes.user")
FolderNode = lazy_type("FolderNode", ".nodes.folder")
TaskNode = lazy_type("TaskNode", ".nodes.task")
SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
VersionNode = lazy_type("VersionNode", ".nodes.version")
RepresentationNode = lazy_type("RepresentationNode", ".nodes.representation")


# Cursor is not a part of base edge, because the order matters and
# cursor is nullable, while node is not, so constructed edge complains
# about required field following optional one.

@strawberry.type
class BaseEdge:
    pass


@strawberry.type
class ProjectEdge(BaseEdge):
    node: ProjectNode = strawberry.field(description="The project node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class UserEdge(BaseEdge):
    node: UserNode = strawberry.field(description="The user node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class FolderEdge(BaseEdge):
    node: FolderNode = strawberry.field(description="The folder node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class TaskEdge(BaseEdge):
    node: TaskNode = strawberry.field(description="The task node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class SubsetEdge(BaseEdge):
    node: SubsetNode = strawberry.field(description="Subset node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class VersionEdge(BaseEdge):
    node: VersionNode = strawberry.field(description="Version node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class RepresentationEdge(BaseEdge):
    node: RepresentationNode = strawberry.field(
        description="Representation node"
    )
    cursor: str | None = strawberry.field(default=None)
