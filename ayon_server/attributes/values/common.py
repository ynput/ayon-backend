import functools
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from ayon_server.entities.core.attrib import AttributeLibrary
    from ayon_server.entities.models import ModelSet

# Entity types, which inherit attributes (from the parent folders and the project)
INHERITING_ENTITY_TYPES = frozenset({"folder", "task"})


@functools.cache
def _model_sets() -> dict[str, "ModelSet"]:
    # Imported here: the entities use the attribute value helpers
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

    return {
        entity_class.entity_type: entity_class.model
        for entity_class in (
            FolderEntity,
            ProductEntity,
            ProjectEntity,
            RepresentationEntity,
            TaskEntity,
            UserEntity,
            VersionEntity,
            WorkfileEntity,
        )
    }


def get_model_set(entity_type: str) -> "ModelSet | None":
    """Return the model set of the entity type (None for unknown types)."""
    return _model_sets().get(entity_type)


@functools.cache
def get_attribute_library() -> "AttributeLibrary":
    """Return the attribute library (a singleton, which reloads in place)."""
    # Imported here: the entities use the attribute value helpers
    from ayon_server.entities.core.attrib import attribute_library

    return attribute_library


def attrib_errors(model: type[BaseModel], values: dict[str, Any]) -> dict[str, str]:
    """Validate values using an attribute model.

    Return {attribute name: error message} of the invalid values.
    Attribute models are flat, so all invalid values are reported at once.
    Missing values of required attributes are not reported.
    """
    try:
        model.__pydantic_validator__.validate_python(values)
    except ValidationError as e:
        return {
            str(error["loc"][0]): error["msg"]
            for error in e.errors()
            if error["loc"] and str(error["loc"][0]) in values
        }
    return {}
