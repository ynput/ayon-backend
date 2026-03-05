from typing import TYPE_CHECKING, Annotated

import strawberry

from ayon_server.graphql.types import BaseEdge

if TYPE_CHECKING:
    from .nodes.activity import ActivityNode
    from .nodes.entity_list import EntityListNode
    from .nodes.event import EventNode
    from .nodes.folder import FolderNode
    from .nodes.kanban import KanbanNode
    from .nodes.product import ProductNode
    from .nodes.project import ProjectNode
    from .nodes.representation import RepresentationNode
    from .nodes.task import TaskNode
    from .nodes.user import UserNode
    from .nodes.version import VersionNode
    from .nodes.workfile import WorkfileNode


@strawberry.type
class ProjectEdge(BaseEdge):
    node: Annotated["ProjectNode", strawberry.lazy(".nodes.project")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class UserEdge(BaseEdge):
    node: Annotated["UserNode", strawberry.lazy(".nodes.user")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class FolderEdge(BaseEdge):
    node: Annotated["FolderNode", strawberry.lazy(".nodes.folder")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class TaskEdge(BaseEdge):
    node: Annotated["TaskNode", strawberry.lazy(".nodes.task")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class ProductEdge(BaseEdge):
    node: Annotated["ProductNode", strawberry.lazy(".nodes.product")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class VersionEdge(BaseEdge):
    node: Annotated["VersionNode", strawberry.lazy(".nodes.version")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class RepresentationEdge(BaseEdge):
    node: Annotated["RepresentationNode", strawberry.lazy(".nodes.representation")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class WorkfileEdge(BaseEdge):
    node: Annotated["WorkfileNode", strawberry.lazy(".nodes.workfile")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class EventEdge(BaseEdge):
    node: Annotated["EventNode", strawberry.lazy(".nodes.event")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class ActivityEdge(BaseEdge):
    node: Annotated["ActivityNode", strawberry.lazy(".nodes.activity")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class KanbanEdge(BaseEdge):
    node: Annotated["KanbanNode", strawberry.lazy(".nodes.kanban")]
    cursor: str | None = strawberry.field(default=None)


@strawberry.type
class EntityListEdge(BaseEdge):
    node: Annotated["EntityListNode", strawberry.lazy(".nodes.entity_list")]
    cursor: str | None = strawberry.field(default=None)
