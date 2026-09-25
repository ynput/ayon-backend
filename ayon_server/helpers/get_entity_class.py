from typing import Literal, overload

from ayon_server.entities import (
    FolderEntity,
    ProductEntity,
    ProjectEntity,
    RepresentationEntity,
    TaskEntity,
    UserEntity,
    VersionEntity,
    WorkfileEntity,
)
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.entities.core.base import BaseEntity

FolderLiteral = Literal["folder"]
TaskLiteral = Literal["task"]
ProductLiteral = Literal["product"]
VersionLiteral = Literal["version"]
RepresentationLiteral = Literal["representation"]
WorkfileLiteral = Literal["workfile"]
ProjectLiteral = Literal["project"]
UserLiteral = Literal["user"]


@overload
def get_entity_class(entity_type: FolderLiteral) -> type[FolderEntity]: ...
@overload
def get_entity_class(entity_type: TaskLiteral) -> type[TaskEntity]: ...
@overload
def get_entity_class(entity_type: ProductLiteral) -> type[ProductEntity]: ...
@overload
def get_entity_class(entity_type: VersionLiteral) -> type[VersionEntity]: ...
@overload
def get_entity_class(
    entity_type: RepresentationLiteral,
) -> type[RepresentationEntity]: ...
@overload
def get_entity_class(entity_type: WorkfileLiteral) -> type[WorkfileEntity]: ...
# Projects and users are not project-level entities, but the generic `str`
# overload below keeps its return type (used by addons with project-level
# entity types), so these two overloads overlap with it intentionally.
@overload
def get_entity_class(  # type: ignore[overload-overlap]
    entity_type: ProjectLiteral,
) -> type[ProjectEntity]: ...
@overload
def get_entity_class(  # type: ignore[overload-overlap]
    entity_type: UserLiteral,
) -> type[UserEntity]: ...


@overload
def get_entity_class(entity_type: str) -> type[ProjectLevelEntity]: ...


def get_entity_class(entity_type: str) -> type[BaseEntity]:
    """Return the entity class of the given entity type.

    This is the one mapping of entity types to their classes
    (used by addons as well). Raises ValueError for unknown types.
    """
    entity_class = _ENTITY_CLASSES.get(entity_type)
    if entity_class is None:
        raise ValueError(f"Invalid entity type: {entity_type}")
    return entity_class


_ENTITY_CLASSES: dict[str, type[BaseEntity]] = {
    "folder": FolderEntity,
    "task": TaskEntity,
    "product": ProductEntity,
    "version": VersionEntity,
    "representation": RepresentationEntity,
    "workfile": WorkfileEntity,
    "project": ProjectEntity,
    "user": UserEntity,
}
