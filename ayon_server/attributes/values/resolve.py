from dataclasses import dataclass
from typing import Any

from ayon_server.utils import json_dumps

from .common import INHERITING_ENTITY_TYPES, get_attribute_library
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


# Inherited values are shared by many entities (all entities of a project
# inherit the same project values, siblings the same parent values), so
# they are resolved once. Key: (entity type, attribute library revision,
# project values as JSON, parent values as JSON)
_inherited_cache: dict[tuple[str, int, str, str], dict[str, Any]] = {}
_INHERITED_CACHE_LIMIT = 4096


def _resolve_inherited(
    entity_type: str,
    project: dict[str, Any] | None,
    inherited: dict[str, Any] | None,
    label: str,
) -> dict[str, Any]:
    attribute_library = get_attribute_library()
    key = (
        entity_type,
        attribute_library.revision,
        json_dumps(project) if project else "",
        json_dumps(inherited) if inherited else "",
    )
    if (result := _inherited_cache.get(key)) is not None:
        return result

    inheritable = set(attribute_library.inheritable_attributes())
    result = {}
    layers = (
        ("default attributes", attribute_library.project_defaults),
        ("project attributes", project),
        ("inherited attributes", inherited),
    )
    for layer_label, layer_values in layers:
        layer = valid_attrib(entity_type, layer_values, f"{layer_label} of {label}")
        for name, value in layer.items():
            if name in inheritable:
                result[name] = value

    if len(_inherited_cache) >= _INHERITED_CACHE_LIMIT:
        _inherited_cache.clear()
    _inherited_cache[key] = result
    return result


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

    # A copy, the cached values are shared
    inherited_values = dict(_resolve_inherited(entity_type, project, inherited, label))
    return ResolvedAttrib(
        values={**inherited_values, **own_values},
        own=list(own_values),
        inherited=inherited_values,
    )
