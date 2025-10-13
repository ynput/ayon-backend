__all__ = ["OPModel", "Field", "camelize"]

import re
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel

from ayon_server.exceptions import BadRequestException
from ayon_server.models import (
    RestField as Field,  # backwards compatibility
)
from ayon_server.models import (
    RestModel as OPModel,  # backwards compatibility
)
from ayon_server.utils import camelize  # backwards compatibilitycamelize

#
# Common constants and types used everywhere
#

Platform = Literal["windows", "linux", "darwin"]
SimpleValue = str | int | float | bool

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

#
# Common regexes
#

ENTITY_ID_REGEX = r"^[0-f]{32}$"
ENTITY_ID_EXAMPLE = "c10d5bc73dcab7da4cba0f3e0b3c0aea"
TOPIC_REGEX = r"^[a-zA-Z][a-zA-Z0-9_\.\*]{2,64}$"

# labels should not contain single quotes or semicolons (sql injection prevention)
LABEL_REGEX = r"^[^';]*$"

# entity names
NAME_REGEX = r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]*[a-zA-Z0-9_])?$"
# statuses and type names (folder type, task type) can also contain spaces
STATUS_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_ \-]{1,64}[a-zA-Z0-9_]$"
TYPE_NAME_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_ \-]{1,64}[a-zA-Z0-9_]$"

# user names shouldn't start or end with underscores
USER_NAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_\.\-]*[a-zA-Z0-9]$"

# project name cannot contain - / . (sql hard limit for schema names)
PROJECT_NAME_REGEX = r"^[a-zA-Z0-9_]*$"
ATTRIBUTE_NAME_REGEX = "^[a-zA-Z0-9]{2,64}$"

# TODO: consider length limit for project code
PROJECT_CODE_REGEX = r"^[a-zA-Z0-9_][a-zA-Z0-9_]*[a-zA-Z0-9_]$"

# api key can contain alphanumeric characters and hyphens
API_KEY_REGEX = r"^[a-zA-Z0-9\-]*$"
SEMVER_REGEX = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"  # noqa: E501
EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


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


def validate_email(email: str) -> str:
    """Validate email."""
    if not re.match(EMAIL_REGEX, email):
        raise BadRequestException(f"Invalid email: '{email}'")
    return email


def validate_email_list(emails: list[str]) -> list[str]:
    """Validate list of emails."""
    return [validate_email(email) for email in emails]


def validate_name_list(names: list[str], regex: str = NAME_REGEX) -> list[str]:
    """Validate list of names."""
    return [validate_name(name, regex) for name in names]


def validate_status_list(statuses: list[str]) -> list[str]:
    """Validate list of statuses."""
    regex = STATUS_REGEX
    return [validate_name(status, regex) for status in statuses]


def validate_type_name_list(type_names: list[str]) -> list[str]:
    """Validate list of type names."""
    regex = TYPE_NAME_REGEX
    return [validate_name(type_name, regex) for type_name in type_names]


def validate_user_name_list(names: list[str]) -> list[str]:
    """Validate list of user names."""
    return [validate_user_name(name) for name in names]


def validate_topic_list(topics: list[str]) -> list[str]:
    """Validate list of topics."""
    result = []
    for topic in topics:
        if not re.match(TOPIC_REGEX, topic):
            raise BadRequestException(
                f"Topic '{topic}' does not match regex '{TOPIC_REGEX}'"
            )
        result.append(topic.replace("*", "%"))
    return result


def sanitize_string_list(strings: list[str]) -> list[str]:
    """Make list of strings safe to use in SQL queries."""
    return [s.replace("'", "''") for s in strings]


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


def normalize_to_dict(s: dict[Any, Any] | BaseModel) -> dict[Any, Any]:
    """Normalize the input data to a dictionary format.

    The input data can be either a dictionary or an instance of a Pydantic BaseModel.

    Raises:
    ValueError: If the input data is neither a dictionary nor a Pydantic BaseModel.
    """

    if isinstance(s, dict):
        return s
    elif isinstance(s, BaseModel):
        return s.dict()
    raise ValueError(f"Can't normalize {s}")
