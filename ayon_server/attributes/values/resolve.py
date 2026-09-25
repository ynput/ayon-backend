from dataclasses import dataclass
from typing import Any

from .common import INHERITING_ENTITY_TYPES, get_attribute_library, get_model_set


@dataclass
class ResolvedAttrib:
    #: Attribute values of the entity (own values over the inherited ones)
    values: dict[str, Any]
    #: Names of the attributes set on the entity itself
    own: list[str]
    #: Values inherited from the parents, the project and the defaults
    #: (also for the attributes set on the entity itself)
    inherited: dict[str, Any]


def resolve_attrib(
    entity_type: str,
    own: dict[str, Any] | None,
    *,
    inherited: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> ResolvedAttrib:
    """Resolve the attribute values of an entity from the stored values.

    Used by both REST (entities) and GraphQL, so they return the same values.

    Folders and tasks inherit attributes. Each inheritable attribute
    has the first value set in the following order:

    1. own value of the entity
    2. value inherited from the parent folders (`inherited`,
       the exported attributes of the parent)
    3. project value (`project`)
    4. default value of the attribute definition

    Other entity types have their own values and the defaults of the
    attribute definitions (only project attributes have defaults).

    Stored values are not validated (they were, when they were written).
    None values and attributes without a definition are ignored.
    """
    model_set = get_model_set(entity_type)
    if model_set is None:
        own_values = {k: v for k, v in (own or {}).items() if v is not None}
        return ResolvedAttrib(values=own_values, own=list(own_values), inherited={})

    defined = model_set.attrib_model.__pydantic_fields__
    own_values = {
        name: value
        for name, value in (own or {}).items()
        if value is not None and name in defined
    }

    if entity_type not in INHERITING_ENTITY_TYPES:
        return ResolvedAttrib(
            values={**model_set.defaults, **own_values},
            own=list(own_values),
            inherited={},
        )

    inheritable = get_attribute_library().inheritable
    inherited_values = dict(model_set.inherited_defaults)
    for layer in (project, inherited):
        if layer:
            inherited_values.update(
                {
                    name: value
                    for name, value in layer.items()
                    if value is not None and name in inheritable and name in defined
                }
            )

    return ResolvedAttrib(
        values={**inherited_values, **own_values},
        own=list(own_values),
        inherited=inherited_values,
    )
