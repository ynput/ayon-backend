from datetime import datetime
from typing import Any, Literal

from ayon_server.entities.core import attribute_library
from ayon_server.entities.user import UserEntity

ATTRIB_WHITELIST = [
    "fullName",
    "avatarUrl",
]


def process_attrib_data(
    entity_type: str,
    own_attrib: dict[str, Any],
    *,
    user: UserEntity,
    project_name: str | None = None,
    inherited_attrib: dict[str, Any] | None = None,
    project_attrib: dict[str, Any] | None = None,
    list_attribute_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attr_limit: list[str] | Literal["all"] = []

    if user.is_guest:
        # Guest users have no access to attributes
        attr_limit = ["fullName"]

    elif user.is_manager:
        # Managers and admins have access to all attributes
        attr_limit = "all"

    elif (perms := user.permissions(project_name)) is None:
        # This shouldn't happen - projects shouldn't load
        # without permissions, this would fail earlier
        # but just in case
        attr_limit = []

    elif perms.attrib_read.enabled:
        attr_limit = perms.attrib_read.attributes

    else:
        attr_limit = "all"

    if attr_limit != "all":
        for k in ATTRIB_WHITELIST:
            if k not in attr_limit:
                attr_limit.append(k)

    # A copy: own_attrib is the node's own attribute dict, which must not
    # get the inherited values (ownAttrib lists its keys)
    data = dict(own_attrib or {})
    if entity_type in {"folder", "task"}:
        # Apply inherited and project attributes for folders and tasks
        # (other entities do not inherit attributes)
        if inherited_attrib is not None:
            for key in attribute_library.inheritable_attributes():
                if data.get(key) is not None:
                    continue
                if key in inherited_attrib:
                    data[key] = inherited_attrib[key]

        project_attrib = {
            **attribute_library.project_defaults,
            **(project_attrib or {}),
        }
        if project_attrib:
            for key in attribute_library.inheritable_attributes():
                if data.get(key) is not None:
                    continue
                if key in project_attrib:
                    data[key] = project_attrib[key]

    if not data:
        return {}

    result = {}
    for key, value in data.items():
        if not (attr_limit == "all" or key in attr_limit):
            continue

        if list_attribute_config and key in own_attrib and key in list_attribute_config:
            attr_type = list_attribute_config[key]
        else:
            try:
                attr = attribute_library.by_name_scoped(entity_type, key)
            except KeyError:
                # Attribute not defined for this entity type
                continue
            attr_type = attr["type"]

        if attr_type == "datetime":
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    # If the value is not a valid ISO format, skip it
                    continue

        result[key] = value

    return result


# Python types of the values, which do not need to be converted
_NATIVE_TYPES: dict[str, type | tuple[type, ...]] = {
    "integer": int,
    "float": float,
    "string": str,
    "boolean": bool,
    "list_of_strings": list,
    "list_of_integers": list,
    "list_of_any": list,
    "list_of_submodels": list,
    "dict": dict,
}

# (library revision, entity type) -> {name: (type, native type, default)}
_attrib_specs: dict[tuple[int, str], dict[str, tuple[str | None, Any, Any]]] = {}


def _get_attrib_specs(entity_type: str) -> dict[str, tuple[str | None, Any, Any]]:
    key = (attribute_library.revision, entity_type)
    if (specs := _attrib_specs.get(key)) is None:
        _attrib_specs.clear()
        specs = {}
        for attr in attribute_library[entity_type]:
            attr_type = attr.get("type")
            specs[attr["name"]] = (
                attr_type,
                _NATIVE_TYPES.get(attr_type or "", ()),
                attr.get("default"),
            )
        _attrib_specs[key] = specs
    return specs


def _serialize_attrib_value(attr_type: str | None, value: Any) -> Any:
    """Serialize an attribute value the same way typed GraphQL fields did."""
    if value is None:
        return None
    try:
        match attr_type:
            case "integer":
                if isinstance(value, float) and value.is_integer():
                    return int(value)
                if isinstance(value, str):
                    return int(value)
            case "float":
                if isinstance(value, int | str) and not isinstance(value, bool):
                    return float(value)
            case "string":
                if isinstance(value, bool):
                    return "true" if value else "false"
                if not isinstance(value, str):
                    return str(value)
            case "datetime":
                if isinstance(value, str):
                    value = datetime.fromisoformat(value)
                if isinstance(value, datetime):
                    return value.isoformat()
    except (ValueError, TypeError):
        pass
    return value


def attrib_to_json(
    entity_type: str,
    data: dict[str, Any],
    names: list[str] | None = None,
    legacy_selection: list[str] | None = None,
) -> dict[str, Any]:
    """Return attribute values for the `attrib` GraphQL field.

    - `names`: return only the given attributes (all by default)
    - `legacy_selection`: selection of the former typed `attrib` field
      (`attrib { fps rate: frameRate }`), rewritten by `LegacyAttribSelection`
      to `["fps", "rate:frameRate"]`. Every selected attribute is returned
      (None or the default value when missing) under its alias.

    Values are converted the same way the typed field did
    (e.g. datetimes to ISO strings, integral floats of integer attributes
    to ints), so the result is the same.
    """
    specs = _get_attrib_specs(entity_type)

    def serialize(name: str, value: Any) -> Any:
        if (spec := specs.get(name)) is None:
            return value
        attr_type, native_type, default = spec
        if value is None:
            value = default
            if value is None:
                return None
        if native_type and isinstance(value, native_type):
            if not (isinstance(value, bool) and attr_type != "boolean"):
                return value
        return _serialize_attrib_value(attr_type, value)

    if legacy_selection is not None:
        result: dict[str, Any] = {}
        for item in legacy_selection:
            alias, _, name = item.partition(":")
            name = name or alias
            if name == "__typename":
                result[alias] = f"{entity_type.capitalize()}AttribType"
            else:
                result[alias] = serialize(name, data.get(name))
        return result

    if names is not None:
        return {name: serialize(name, data.get(name)) for name in names}
    return {name: serialize(name, value) for name, value in data.items()}
