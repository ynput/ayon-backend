from datetime import datetime
from typing import Any, Literal

from ayon_server.attributes.values import ResolvedAttrib, resolve_attrib
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
    label: str | None = None,
    resolved: ResolvedAttrib | None = None,
) -> dict[str, Any]:
    """Return the attribute values of an entity the user can read.

    The values are resolved from the own, inherited and project values
    by `resolve_attrib` (the same way as in REST), unless `resolved`
    values are provided. List item attributes (`list_attribute_config`)
    are not entity attributes and are used as they are.
    """
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

    list_keys = set(list_attribute_config or {})
    if resolved is None:
        resolved = resolve_attrib(
            entity_type,
            {k: v for k, v in (own_attrib or {}).items() if k not in list_keys},
            inherited=inherited_attrib,
            project=project_attrib,
            label=label or f"{entity_type} in {project_name}",
        )
    data = {
        **resolved.values,
        **{k: v for k, v in (own_attrib or {}).items() if k in list_keys},
    }

    if not data:
        return {}

    result = {}
    for key, value in data.items():
        if not (attr_limit == "all" or key in attr_limit):
            continue
        # Entity attributes are already validated and converted (resolve_attrib),
        # list item attributes are used as they are stored
        if (
            key in list_keys
            and list_attribute_config
            and list_attribute_config[key] == "datetime"
            and isinstance(value, str)
        ):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                continue
        result[key] = value

    return result


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
      (None when missing) under its alias.

    `data` are the resolved values (see resolve_attrib), which already
    include the inherited and default values.

    The values are already converted to the attribute types by
    resolve_attrib (the same way the typed field did). Only datetimes
    are converted to ISO strings (JSON).
    """

    def serialize(value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value

    if legacy_selection is not None:
        result: dict[str, Any] = {}
        for item in legacy_selection:
            alias, _, name = item.partition(":")
            name = name or alias
            if name == "__typename":
                result[alias] = f"{entity_type.capitalize()}AttribType"
            else:
                result[alias] = serialize(data.get(name))
        return result

    if names is not None:
        return {name: serialize(data.get(name)) for name in names}
    return {name: serialize(value) for name, value in data.items()}
