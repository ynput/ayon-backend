from typing import Literal, Type

import strawberry

from openpype.entities.user import UserEntity


def parse_json_data(target_type, data):
    if not data:
        return target_type()
    result = {}
    for key in target_type.__dataclass_fields__.keys():
        if key in data:
            result[key] = data[key]
    return target_type(**result)


def parse_attrib_data(
    target_type,
    data: dict,
    user: UserEntity,
    project_name: str | None = None,
):
    """ACL agnostic attribute list parser"""

    attr_limit: list[str] | Literal["all"] = []

    if user.is_manager:
        attr_limit = "all"
    elif (perms := user.permissions(project_name)) is None:
        attr_limit = []  # This shouldn't happen
    elif perms.attrib_read.enabled:
        attr_limit = perms.attrib_read.attributes

    if not data:
        return target_type()
    result = {}
    for key in target_type.__dataclass_fields__.keys():
        if key in data:
            if attr_limit == "all" or key in attr_limit:
                result[key] = data[key]
    return target_type(**result)


def lazy_type(name: str, module: str) -> Type[strawberry.LazyType]:
    """Create a lazy type for the given module and name.

    When used, module path must be relative
    to THIS file (root of the graphql module)
    e.g. `.nodes.node` or `.connection`
    """
    return strawberry.LazyType[name, module]  # type: ignore
