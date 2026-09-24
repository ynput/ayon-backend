"""GraphQL types of entity attributes.

Attribute types (`FolderAttribType`...) are generated from the pydantic
attribute models of the entities. When the attributes change at runtime,
the types are updated in place (node resolvers refer to the original
classes in their annotations) and the GraphQL schema is rebuilt.
"""

import dataclasses
from typing import TYPE_CHECKING, Any

import strawberry
from pydantic import BaseModel
from strawberry.experimental.pydantic import type as pydantic_type

from ayon_server.logging import log_traceback

if TYPE_CHECKING:
    from ayon_server.entities.models import ModelSet


# Registry of the attribute types: (strawberry type, model set)
_attrib_types: list[tuple[type, "ModelSet"]] = []

# Class attributes created by the dataclass / strawberry decorators,
# which depend on the list of fields
_FIELD_DEPENDENT_ATTRS = (
    "__init__",
    "__repr__",
    "__eq__",
    "__match_args__",
    "__annotations__",
    dataclasses._FIELDS,  # type: ignore[attr-defined]
)


def _build_type(model: type[BaseModel], cls: type) -> Any:
    """Create a strawberry type with the fields of the given model."""
    if model.model_fields:
        strawberry_type: Any = pydantic_type(model=model, all_fields=True)(cls)
    else:
        # GraphQL object types must have at least one field. That happens
        # when no attribute is enabled for the entity type.
        cls.__annotations__ = {"empty": bool | None}
        cls.empty = strawberry.field(  # type: ignore[attr-defined]
            default=None,
            description="Placeholder. No attributes are defined.",
        )
        strawberry_type = strawberry.type(cls)
    strawberry_type._pydantic_type = model
    return strawberry_type


def create_attrib_type(model_set: "ModelSet", cls: type) -> type:
    """Create a strawberry type from the attribute model of the entity."""
    strawberry_type = _build_type(model_set.attrib_model, cls)
    _attrib_types.append((strawberry_type, model_set))
    return strawberry_type


def refresh_attrib_type(strawberry_type: type, model_set: "ModelSet") -> None:
    """Update the fields of an existing attribute type to the current model."""
    model = model_set.attrib_model
    if getattr(strawberry_type, "_pydantic_type", None) is model:
        return

    template = type(
        strawberry_type.__name__,
        (),
        {"__module__": strawberry_type.__module__},
    )
    fresh = _build_type(model, template)

    for attr in _FIELD_DEPENDENT_ATTRS:
        if attr in fresh.__dict__:
            setattr(strawberry_type, attr, fresh.__dict__[attr])

    fields = fresh.__strawberry_definition__.fields
    for field in fields:
        field.origin = strawberry_type
    strawberry_type.__strawberry_definition__.fields = fields  # type: ignore
    strawberry_type._pydantic_type = model  # type: ignore
    model._strawberry_type = strawberry_type  # type: ignore


def refresh_attrib_types() -> bool:
    """Refresh all attribute types. Return True if any of them changed."""
    changed = False
    for strawberry_type, model_set in _attrib_types:
        if getattr(strawberry_type, "_pydantic_type", None) is model_set.attrib_model:
            continue
        try:
            refresh_attrib_type(strawberry_type, model_set)
        except Exception:
            log_traceback(f"Unable to update GraphQL type {strawberry_type.__name__}")
            continue
        changed = True
    return changed
