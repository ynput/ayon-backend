from dataclasses import dataclass
from typing import Any

from .common import INHERITING_ENTITY_TYPES, get_attribute_library, get_model_set
from .valid import valid_attrib


@dataclass
class ResolvedAttrib:
    #: Attribute values of the entity (own values over the inherited ones)
    values: dict[str, Any]
    #: Names of the attributes set on the entity itself (with a valid value)
    own: list[str]
    #: Values inherited from the parents, the project and the defaults
    #: (also for the attributes set on the entity itself)
    inherited: dict[str, Any]


def resolve_attrib(
    entity_type: str,
    own: dict[str, Any] | None,
    *,
    label: str,
    inherited: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
) -> ResolvedAttrib:
    """Resolve the attribute values of an entity from the stored values.

    Used by both REST (entities) and GraphQL, so they return the same values.

    Folders and tasks inherit attributes. The first valid value of each
    inheritable attribute is used, in the following order:

    1. own value of the entity
    2. value inherited from the parent folders (`inherited`,
       the exported attributes of the parent)
    3. project value (`project`)
    4. default value of the attribute definition

    Other entity types only have their own values. Invalid values, None
    values and attributes without a definition are ignored
    (see `valid_attrib`).
    """
    # None means "not set" (the inherited value is used)
    own_values = {
        name: value
        for name, value in valid_attrib(entity_type, own, label).items()
        if value is not None
    }

    if entity_type not in INHERITING_ENTITY_TYPES:
        return ResolvedAttrib(values=own_values, own=list(own_values), inherited={})

    inheritable = get_attribute_library().inheritable
    model_set = get_model_set(entity_type)
    assert model_set is not None
    inherited_values = dict(model_set.inherited_defaults)
    for layer_label, layer_values in (
        ("project attributes", project),
        ("inherited attributes", inherited),
    ):
        layer = valid_attrib(entity_type, layer_values, f"{layer_label} of {label}")
        inherited_values.update(
            {name: value for name, value in layer.items() if name in inheritable}
        )

    return ResolvedAttrib(
        values={**inherited_values, **own_values},
        own=list(own_values),
        inherited=inherited_values,
    )
