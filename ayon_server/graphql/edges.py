from typing import TYPE_CHECKING

import strawberry
from strawberry import LazyType

from ayon_server.graphql.types import BaseEdge

if TYPE_CHECKING:
    from ayon_server.graphql.nodes.activity import ActivityNode
    from ayon_server.graphql.nodes.event import EventNode
    from ayon_server.graphql.nodes.folder import FolderNode
    from ayon_server.graphql.nodes.product import ProductNode
    from ayon_server.graphql.nodes.project import ProjectNode
    from ayon_server.graphql.nodes.representation import RepresentationNode
    from ayon_server.graphql.nodes.task import TaskNode
    from ayon_server.graphql.nodes.user import UserNode
    from ayon_server.graphql.nodes.version import VersionNode
    from ayon_server.graphql.nodes.workfile import WorkfileNode
else:
    ActivityNode = LazyType["ActivityNode", ".nodes.activity"]
    ProjectNode = LazyType["ProjectNode", ".nodes.project"]
    UserNode = LazyType["UserNode", ".nodes.user"]
    FolderNode = LazyType["FolderNode", ".nodes.folder"]
    TaskNode = LazyType["TaskNode", ".nodes.task"]
    ProductNode = LazyType["ProductNode", ".nodes.product"]
    VersionNode = LazyType["VersionNode", ".nodes.version"]
    RepresentationNode = LazyType["RepresentationNode", ".nodes.representation"]
    EventNode = LazyType["EventNode", ".nodes.event"]
    WorkfileNode = LazyType["WorkfileNode", ".nodes.workfile"]
    BaseNode = LazyType["BaseNode", ".nodes.common"]


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
class ProductEdge(BaseEdge):
    node: ProductNode = strawberry.field(description="Product node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class VersionEdge(BaseEdge):
    node: VersionNode = strawberry.field(description="Version node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class RepresentationEdge(BaseEdge):
    node: RepresentationNode = strawberry.field(description="Representation node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class WorkfileEdge(BaseEdge):
    node: WorkfileNode = strawberry.field(description="Workfile node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class EventEdge(BaseEdge):
    node: EventNode = strawberry.field(description="Event node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class ActivityEdge(BaseEdge):
    node: ActivityNode = strawberry.field(description="The activity node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class InboxEdge(BaseEdge):
    node: ActivityNode = strawberry.field(description="The inbox node")
    cursor: str | None = strawberry.field(default=None)
