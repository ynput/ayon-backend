__all__ = [
    "ProjectsConnection",
    "UsersConnection",
    "FoldersConnection",
    "TasksConnection",
    "SubsetsConnection",
    "VersionsConnection",
    "RepresentationsConnection",
    "PageInfo",
]

import strawberry

from .edges import (
    FolderEdge,
    ProjectEdge,
    RepresentationEdge,
    SubsetEdge,
    TaskEdge,
    UserEdge,
    VersionEdge,
)


@strawberry.type
class PageInfo:
    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None


@strawberry.type
class BaseConnection:
    page_info: PageInfo = strawberry.field(
        default_factory=PageInfo, description="Pagination information"
    )


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
