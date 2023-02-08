"""Model generator.

Warning! We need to use typing.List in the models,
since Python 3.10 syntax does not work with Strawberry yet.
"""

import time
import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field, create_model

from ayon_server.types import AttributeType

C = TypeVar("C", bound=type)

#
# Field types
#


FIELD_TYPES = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "datetime": datetime,
    "list_of_strings": List[str],
    "list_of_integers": List[int],
    "list_of_any": List[Any],
    "list_of_submodels": List[Any],
    "dict": dict,
}

#
# Factories
#


def new_id() -> str:
    """Create a new entity ID."""
    return str(uuid.uuid1()).replace("-", "")


def current_time() -> datetime:
    """Return current time."""
    return datetime.now()


FIELD_FACORIES = {
    "list": list,
    "dict": dict,
    "now": current_time,
    "uuid": new_id,
}

#
# Field definition
#

# TODO: Implement this
# 'exclude',
# 'include',
# 'const',
# 'multiple_of',
# 'allow_mutation',
# 'repr',
# 'extra',


class EnumFieldDefinition(BaseModel):
    """Enum field definition."""

    value: str
    label: str


class FieldDefinition(BaseModel):
    """Field definition model."""

    # Required
    name: str = Field(title="Name of the field")
    required: bool = Field(title="Required field", default=False)

    type: AttributeType = Field(default="string", title="Field data type")
    submodel: Optional[Any]
    list_of_submodels: Optional[Any]
    # Descriptive
    title: Optional[str] = Field(title="Nice field title")
    description: Optional[str] = Field(title="Field description")
    example: Optional[Any] = Field(title="Field example")

    # Default value
    default: Optional[Any] = Field(title="Field default value")
    factory: Optional[Literal["list", "dict", "now", "uuid", "time"]] = Field(
        title="Default factory",
        description="Name of the function to be used to create default values",
    )

    # Validation
    gt: Union[int, float, None] = Field(title="Greater than")
    ge: Union[int, float, None] = Field(title="Geater or equal")
    lt: Union[int, float, None] = Field(title="Less")
    le: Union[int, float, None] = Field(title="Less or equal")
    min_length: Optional[int] = Field(title="Minimum length")
    max_length: Optional[int] = Field(title="Maximum length")
    min_items: Optional[int] = Field(title="Minimum items")
    max_items: Optional[int] = Field(title="Maximum items")
    regex: Optional[str] = Field(title="Field regex")
    enum: Optional[list[EnumFieldDefinition]] = Field(None, title="Enum values")


def generate_model(
    model_name: str,
    field_data: list[dict[str, Any]],
    config: C | None = None,
) -> Type[BaseModel]:
    """Create a new model from a given field set."""
    fields = {}

    for fdef_data in field_data:
        fdef = FieldDefinition(**fdef_data)
        field = {}

        #
        # Documentation and validation
        #

        for k in (
            # Descriptive tags
            "title",
            "description",
            "example",
            # Numeric validators
            "gt",
            "ge",
            "lt",
            "le",
            # String validators
            "min_length",
            "max_length",
            "regex",
            # Array validators
            "min_items",
            "max_items",
            # Enum
            "enum",
        ):
            if getattr(fdef, k):
                field[k] = getattr(fdef, k)
        #
        # Default value
        #

        if fdef.submodel:
            field["default_factory"] = fdef.submodel
        elif fdef.type.startswith("list_of_") and fdef.required:
            field["default_factory"] = list
        elif fdef.factory:
            field["default_factory"] = FIELD_FACORIES[fdef.factory]
        elif fdef.default is not None:
            field["default"] = fdef.default
        elif fdef.required:
            field["default"] = ...
        else:
            field["default"] = None

        #
        # Field type
        #

        if fdef.submodel:
            ftype = fdef.submodel
        elif fdef.list_of_submodels:
            assert fdef.list_of_submodels
            ftype = List[fdef.list_of_submodels]  # type: ignore
        elif fdef.type in FIELD_TYPES:
            if fdef.required:
                ftype = FIELD_TYPES[fdef.type]
            else:
                ftype = FIELD_TYPES[fdef.type] | None
        else:
            ftype = Any

        fields[fdef.name] = (ftype, Field(**field))

    return create_model(model_name, __config__=config, **fields)  # type: ignore
