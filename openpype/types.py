__all__ = [
    "OPModel",
    "Field",
]

import re

from typing import Literal, Tuple

from pydantic import BaseModel, Field

from openpype.exceptions import BadRequestException
from openpype.utils import json_dumps, json_loads

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

ColorWithAlpha = Tuple[float, float, float, float]

ENTITY_ID_REGEX = r"^[0-f]{32}$"
ENTITY_ID_EXAMPLE = "c10d5bc73dcab7da4cba0f3e0b3c0aea"
NAME_REGEX = r"^[a-zA-Z0-9_]{2,64}$"
USER_NAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_\.\-]*[a-zA-Z0-9]$"


def validate_name(name: str) -> None:
    """Validate name."""
    if not re.match(NAME_REGEX, name):
        raise BadRequestException(f"Name '{name}' does not match regex '{NAME_REGEX}'")

def validate_user_name(name: str) -> None:
    """Validate user name."""
    if not re.match(USER_NAME_REGEX, name):
        raise BadRequestException(
            f"User name '{name}' does not match regex '{USER_NAME_REGEX}'"
        )

def validate_name_list(names: list) -> None:
    """Validate list of names."""
    for name in names:
        validate_name(name)

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
