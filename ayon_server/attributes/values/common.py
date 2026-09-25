import functools
from typing import TYPE_CHECKING

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
