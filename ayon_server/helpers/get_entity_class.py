from typing import Literal, overload

from ayon_server.entities import (
    FolderEntity,
    ProductEntity,
    RepresentationEntity,
    TaskEntity,
    VersionEntity,
    WorkfileEntity,
)
from ayon_server.entities.core import ProjectLevelEntity

FolderLiteral = Literal["folder"]
TaskLiteral = Literal["task"]
ProductLiteral = Literal["product"]
VersionLiteral = Literal["version"]
RepresentationLiteral = Literal["representation"]
WorkfileLiteral = Literal["workfile"]


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


@overload
def get_entity_class(entity_type: str) -> type[ProjectLevelEntity]: ...


def get_entity_class(entity_type: str) -> type[ProjectLevelEntity]:
    entity_class = {
        "folder": FolderEntity,
        "task": TaskEntity,
        "product": ProductEntity,
        "version": VersionEntity,
        "representation": RepresentationEntity,
        "workfile": WorkfileEntity,
    }.get(entity_type)
    if entity_class is None:
        raise ValueError(f"Invalid entity type: {entity_type}")
    return entity_class
