from datetime import datetime
from typing import Any, Literal, TypeVar

from ayon_server.entities.core import attribute_library
from ayon_server.entities.user import UserEntity

ATTRIB_WHITELIST = [
    "fullName",
    "avatarUrl",
]

T = TypeVar("T")


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

    data = own_attrib or {}
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


def parse_attrib_data(
    entity_type: str,
    target_type: type[T],
    own_attrib: dict[str, Any],
    *,
    user: UserEntity,
    project_name: str | None = None,
    inherited_attrib: dict[str, Any] | None = None,
    project_attrib: dict[str, Any] | None = None,
) -> T:
    """ACL agnostic attribute list parser"""

    result = process_attrib_data(
        entity_type,
        own_attrib,
        user=user,
        project_name=project_name,
        inherited_attrib=inherited_attrib,
        project_attrib=project_attrib,
    )

    return target_type(**result)
