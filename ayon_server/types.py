__all__ = [
    "OPModel",
    "Field",
]

import re
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from ayon_server.exceptions import BadRequestException
from ayon_server.utils import json_dumps, json_loads

#
# Common constants and types used everywhere
#

Platform = Literal["windows", "linux", "darwin"]

AccessType = Literal[
    "create",
    "read",
    "update",
    "delete",
    "publish",
]

ProjectLevelEntityType = Literal[
    "folder",
    "product",
    "version",
    "representation",
    "task",
    "workfile",
]

TopLevelEntityType = Literal[
    "project",
    "user",
]

AttributeType = Literal[
    "string",
    "integer",
    "float",
    "boolean",
    "datetime",
    "list_of_strings",
    "list_of_integers",
    "list_of_any",
    "list_of_submodels",
    "dict",
]

ENTITY_ID_REGEX = r"^[0-f]{32}$"
ENTITY_ID_EXAMPLE = "c10d5bc73dcab7da4cba0f3e0b3c0aea"
STATUS_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_ \-]{2,64}[a-zA-Z0-9_]$"
TOPIC_REGEX = r"^[a-zA-Z][a-zA-Z0-9_\.\*]{2,64}$"
LABEL_REGEX = r"^[^';]*$"
NAME_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_\.\-]*[a-zA-Z0-9_]$"
USER_NAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_\.\-]*[a-zA-Z0-9]$"
# project name cannot contain - / .
PROJECT_NAME_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_]*[a-zA-Z0-9_]$"
PROJECT_CODE_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_]*[a-zA-Z0-9_]$"


def validate_name(name: str, regex: str = NAME_REGEX) -> str:
    """Validate name."""
    if not re.match(regex, name):
        raise BadRequestException(f"Name '{name}' does not match regex '{regex}'")
    return name


def validate_user_name(name: str) -> str:
    """Validate user name."""
    if not re.match(USER_NAME_REGEX, name):
        raise BadRequestException(
            f"User name '{name}' does not match regex '{USER_NAME_REGEX}'"
        )
    return name


def validate_name_list(names: list, regex: str = NAME_REGEX) -> list[str]:
    """Validate list of names."""
    return [validate_name(name, regex) for name in names]


def validate_status_list(statuses: list) -> list[str]:
    """Validate list of statuses."""
    regex = STATUS_REGEX
    return [validate_name(status, regex) for status in statuses]


def validate_user_name_list(names: list) -> list[str]:
    """Validate list of user names."""
    return [validate_user_name(name) for name in names]


def validate_topic_list(topics: list) -> list[str]:
    """Validate list of topics."""
    result = []
    for topic in topics:
        if not re.match(TOPIC_REGEX, topic):
            raise BadRequestException(
                f"Topic '{topic}' does not match regex '{TOPIC_REGEX}'"
            )
        result.append(topic.replace("*", "%"))
    return result


#
# Pydantic model used for API requests and responses,
# entity payloads etc.
#


def camelize(src: str) -> str:
    """Convert snake_case to camelCase."""
    components = src.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class OPModel(BaseModel):
    """Base API model."""

    class Config:
        """API model config."""

        orm_mode = True
        allow_population_by_field_name = True
        alias_generator = camelize
        json_loads = json_loads
        json_dumps = json_dumps


#
# Color types (for settings)
#


class ColorRGB_hex(str):
    """Color in RGB hex format.

    Example: #ff0000
    """

    pass


class ColorRGBA_hex(str):
    """Color in RGBA hex format.

    Example: #ff0000ff
    """

    pass


class ColorRGB_uint8(NamedTuple):
    """Color in RGB uint8 format.

    Example: (255, 0, 0)
    """

    r: int
    g: int
    b: int


class ColorRGBA_uint8(NamedTuple):
    """Color in RGBA uint8 format.
    Alpha is specified as float in range 0.0 - 1.0

    Example: (255, 0, 0, 1.0)
    """

    r: int
    g: int
    b: int
    a: float


class ColorRGB_float(NamedTuple):
    """Color in RGB float format.

    Example: (1.0, 0.0, 0.0)
    """

    r: float
    g: float
    b: float


class ColorRGBA_float(NamedTuple):
    """Color in RGBA float format.
    Alpha is specified as float in range 0.0 - 1.0

    Example: (1.0, 0.0, 0.0, 1.0)
    """

    r: float
    g: float
    b: float
    a: float
