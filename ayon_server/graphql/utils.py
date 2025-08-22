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
    own_attrib: dict[str, Any],
    *,
    user: UserEntity,
    project_name: str | None = None,
    inherited_attrib: dict[str, Any] | None = None,
    project_attrib: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attr_limit: list[str] | Literal["all"] = []

    if user.is_external:
        # External users have no access to attributes
        attr_limit = []

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
    if inherited_attrib is not None:
        for key in attribute_library.inheritable_attributes():
            if data.get(key) is not None:
                continue
            if key in inherited_attrib:
                data[key] = inherited_attrib[key]

    project_attrib = {**attribute_library.project_defaults, **(project_attrib or {})}
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

        if attribute_library.by_name(key)["type"] == "datetime":
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    # If the value is not a valid ISO format, skip it
                    continue

        result[key] = value
    return result


def parse_attrib_data(
    target_type: type[T],
    own_attrib: dict[str, Any],
    *,
    user: UserEntity,
    project_name: str | None = None,
    inherited_attrib: dict[str, Any] | None = None,
    project_attrib: dict[str, Any] | None = None,
) -> T:
    """ACL agnostic attribute list parser"""

    result = {
        key: value
        for key, value in process_attrib_data(
            own_attrib,
            user=user,
            project_name=project_name,
            inherited_attrib=inherited_attrib,
            project_attrib=project_attrib,
        ).items()
        if key in target_type.__dataclass_fields__.keys()  # type: ignore
    }

    return target_type(**result)
