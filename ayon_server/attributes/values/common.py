import functools
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from ayon_server.entities.core.attrib import AttributeLibrary
    from ayon_server.entities.models import ModelSet

# Entity types, which inherit attributes (from the parent folders and the project)
INHERITING_ENTITY_TYPES = frozenset({"folder", "task"})


@functools.cache
def get_model_set(entity_type: str) -> "ModelSet | None":
    """Return the model set of the entity type (None for unknown types)."""
    # Imported here: the entities use the attribute value helpers
    from ayon_server.helpers.get_entity_class import get_entity_class

    try:
        return get_entity_class(entity_type).model
    except ValueError:
        return None


@functools.cache
def get_attribute_library() -> "AttributeLibrary":
    """Return the attribute library (a singleton, which reloads in place)."""
    # Imported here: the entities use the attribute value helpers
    from ayon_server.entities.core.attrib import attribute_library

    return attribute_library


def validate_values(
    model: type[BaseModel],
    values: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate attribute values using an attribute model.

    Return the validated values (converted to the attribute types,
    without the invalid ones) and {attribute name: error message}
    of the invalid values. Attribute models are flat, so all invalid
    values are reported at once. Missing values of required attributes
    are not reported. Valid data is validated only once.
    """
    try:
        instance = model.__pydantic_validator__.validate_python(values)
    except ValidationError as e:
        errors = {
            str(error["loc"][0]): error["msg"]
            for error in e.errors()
            if error["loc"] and str(error["loc"][0]) in values
        }
        if not errors:
            # Only required attributes are missing: nothing to convert
            return dict(values), {}
        valid, _ = validate_values(
            model, {k: v for k, v in values.items() if k not in errors}
        )
        return valid, errors
    # Attributes without a definition are ignored by the model
    validated = instance.__dict__
    return {key: validated[key] for key in values if key in validated}, {}
