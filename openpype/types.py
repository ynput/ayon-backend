__all__ = [
    "OPModel",
    "Field",
]

from typing import Literal

from pydantic import BaseModel, Field

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
]

TopLevelEntityType = Literal[
    "project",
    "user",
]

ENTITY_ID_REGEX = r"^[0-f]{32}$"
ENTITY_ID_EXAMPLE = "c10d5bc73dcab7da4cba0f3e0b3c0aea"
NAME_REGEX = r"^[a-zA-Z0-9_]{2,64}$"
USER_NAME_REGEX = r"^[a-zA-Z0-9][a-zA-Z0-9_\.\-]*[a-zA-Z0-9]$"

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
