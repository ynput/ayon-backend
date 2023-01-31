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

AccessType = Literal[
    "create",
    "read",
    "update",
    "delete",
]

ProjectLevelEntityType = Literal[
    "folder",
    "subset",
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
    "list_of_strings",
    "list_of_any",
    "dict",
]

ENTITY_ID_REGEX = r"^[0-f]{32}$"
ENTITY_ID_EXAMPLE = "c10d5bc73dcab7da4cba0f3e0b3c0aea"
NAME_REGEX = r"^[a-zA-Z0-9_]{2,64}$"
TOPIC_REGEX = r"^[a-zA-Z0-9_\.]{2,64}$"
LABEL_REGEX = r"^[^';]*$"
USER_NAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_\.\-]*[a-zA-Z0-9]$"


def validate_name(name: str, regex: str = NAME_REGEX) -> None:
    """Validate name."""
    if not re.match(regex, name):
        raise BadRequestException(f"Name '{name}' does not match regex '{regex}'")


def validate_user_name(name: str) -> None:
    """Validate user name."""
    if not re.match(USER_NAME_REGEX, name):
        raise BadRequestException(
            f"User name '{name}' does not match regex '{USER_NAME_REGEX}'"
        )


def validate_name_list(names: list, regex: str = NAME_REGEX) -> None:
    """Validate list of names."""
    for name in names:
        validate_name(name, regex)


def validate_user_name_list(names: list) -> None:
    """Validate list of user names."""
    for name in names:
        validate_user_name(name)


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
