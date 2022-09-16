import strawberry

from openpype.graphql.edges import (
    EventEdge,
    FolderEdge,
    ProjectEdge,
    RepresentationEdge,
    SubsetEdge,
    TaskEdge,
    UserEdge,
    VersionEdge,
)
from openpype.graphql.types import BaseConnection


@strawberry.type
class ProjectsConnection(BaseConnection):
    edges: list[ProjectEdge] = strawberry.field(default_factory=list)


@strawberry.type
class UsersConnection(BaseConnection):
    edges: list[UserEdge] = strawberry.field(default_factory=list)


@strawberry.type
class FoldersConnection(BaseConnection):
    edges: list[FolderEdge] = strawberry.field(default_factory=list)


@strawberry.type
class TasksConnection(BaseConnection):
    edges: list[TaskEdge] = strawberry.field(default_factory=list)


@strawberry.type
class SubsetsConnection(BaseConnection):
    edges: list[SubsetEdge] = strawberry.field(default_factory=list)


@strawberry.type
class VersionsConnection(BaseConnection):
    edges: list[VersionEdge] = strawberry.field(default_factory=list)


@strawberry.type
class RepresentationsConnection(BaseConnection):
    edges: list[RepresentationEdge] = strawberry.field(default_factory=list)


@strawberry.type
class EventsConnection(BaseConnection):
    edges: list[EventEdge] = strawberry.field(default_factory=list)
