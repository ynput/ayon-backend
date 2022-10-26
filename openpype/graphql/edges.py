from typing import TYPE_CHECKING

import strawberry

from openpype.graphql.types import BaseEdge
from openpype.graphql.utils import lazy_type

if TYPE_CHECKING:
    from openpype.graphql.nodes.event import EventNode
    from openpype.graphql.nodes.folder import FolderNode
    from openpype.graphql.nodes.project import ProjectNode
    from openpype.graphql.nodes.representation import RepresentationNode
    from openpype.graphql.nodes.subset import SubsetNode
    from openpype.graphql.nodes.task import TaskNode
    from openpype.graphql.nodes.user import UserNode
    from openpype.graphql.nodes.version import VersionNode
    from openpype.graphql.nodes.workfile import WorkfileNode
else:
    ProjectNode = lazy_type("ProjectNode", ".nodes.project")
    UserNode = lazy_type("UserNode", ".nodes.user")
    FolderNode = lazy_type("FolderNode", ".nodes.folder")
    TaskNode = lazy_type("TaskNode", ".nodes.task")
    SubsetNode = lazy_type("SubsetNode", ".nodes.subset")
    VersionNode = lazy_type("VersionNode", ".nodes.version")
    RepresentationNode = lazy_type("RepresentationNode", ".nodes.representation")
    EventNode = lazy_type("EventNode", ".nodes.event")
    WorkfileNode = lazy_type("WorkfileNode", ".nodes.workfile")
    BaseNode = lazy_type("BaseNode", ".nodes.common")


@strawberry.type
class ProjectEdge(BaseEdge):
    node: "ProjectNode" = strawberry.field(description="The project node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class UserEdge(BaseEdge):
    node: "UserNode" = strawberry.field(description="The user node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class FolderEdge(BaseEdge):
    node: "FolderNode" = strawberry.field(description="The folder node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class TaskEdge(BaseEdge):
    node: "TaskNode" = strawberry.field(description="The task node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class SubsetEdge(BaseEdge):
    node: "SubsetNode" = strawberry.field(description="Subset node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class VersionEdge(BaseEdge):
    node: "VersionNode" = strawberry.field(description="Version node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class RepresentationEdge(BaseEdge):
    node: "RepresentationNode" = strawberry.field(description="Representation node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class WorkfileEdge(BaseEdge):
    node: "WorkfileNode" = strawberry.field(description="Workfile node")
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class EventEdge(BaseEdge):
    node: "EventNode" = strawberry.field(description="Event node")
    cursor: str | None = strawberry.field(default=None)
