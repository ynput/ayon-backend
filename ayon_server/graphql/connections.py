import strawberry

from ayon_server.graphql.edges import (
    ActivityEdge,
    EventEdge,
    FolderEdge,
    ProductEdge,
    ProjectEdge,
    RepresentationEdge,
    TaskEdge,
    UserEdge,
    VersionEdge,
    WorkfileEdge,
)
from ayon_server.graphql.types import BaseConnection


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
class ProductsConnection(BaseConnection):
    edges: list[ProductEdge] = strawberry.field(default_factory=list)


@strawberry.type
class VersionsConnection(BaseConnection):
    edges: list[VersionEdge] = strawberry.field(default_factory=list)


@strawberry.type
class RepresentationsConnection(BaseConnection):
    edges: list[RepresentationEdge] = strawberry.field(default_factory=list)


@strawberry.type
class WorkfilesConnection(BaseConnection):
    edges: list[WorkfileEdge] = strawberry.field(default_factory=list)


@strawberry.type
class EventsConnection(BaseConnection):
    edges: list[EventEdge] = strawberry.field(default_factory=list)


@strawberry.type
class ActivitiesConnection(BaseConnection):
    edges: list[ActivityEdge] = strawberry.field(default_factory=list)
