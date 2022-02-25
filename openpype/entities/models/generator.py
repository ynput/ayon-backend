"""Model generator.

Warning! We need to use typing.List in the models,
since Python 3.10 syntax does not work with Strawberry yet.
"""

import time
import uuid

from typing import Optional, Literal, List, Any, Union
from pydantic import BaseModel, Field, create_model

#
# Field types
#

FIELD_TYPES = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "list_of_strings": List[str],
    "list_of_integers": List[int],
    "list_of_any": List[Any],
    "dict": dict
}

#
# Factories
#


def new_id():
    """Create a new entity ID."""
    return str(uuid.uuid1()).replace("-", "")


def current_timestamp():
    """Return current unix timestamp."""
    return int(time.time())


FIELD_FACORIES = {
    "list": list,
    "dict": dict,
    "now": current_timestamp,
    "uuid": new_id
}

#
# Field definition
#

# TODO: Implement this
# 'exclude',
# 'include',
# 'const',
# 'multiple_of',
# 'min_items',
# 'max_items',
# 'allow_mutation',
# 'repr',
# 'extra',


class FieldDefinition(BaseModel):
    """Field definition model."""

    # Required
    name: str = Field(title="Name of the field")
    required: bool = Field(title="Required field", default=False)

    # This is rather stupid, but typing.Literal
    # does not allow argument unpacking :-(
    type: Literal[
        "string",
        "integer",
        "float",
        "boolean",
        "list_of_strings",
        "list_of_any",
        "dict"
    ] = Field(
        default="string",
        title="Field data type"
    )
    submodel: Optional[Any]

    # Descriptive
    title: Optional[str] = Field(title="Nice field title")
    description: Optional[str] = Field(title="Field description")
    example: Optional[Any] = Field(title="Field example")

    # Default value
    default: Optional[Any] = Field(title="Field default value")
    factory: Optional[Literal["list", "dict", "now", "uuid"]] = Field(
        title="Default factory",
        description="Name of the function to be used to create default values"
    )

    # Validation
    gt: Union[int, float, None] = Field(title="Greater than")
    ge: Union[int, float, None] = Field(title="Geater or equal")
    lt: Union[int, float, None] = Field(title="Less")
    le: Union[int, float, None] = Field(title="Less or equal")
    min_length: Optional[int] = Field(title="Minimum length")
    max_length: Optional[int] = Field(title="Maximum length")
    regex: Optional[str] = Field(title="Field regex")


def generate_model(
    model_name: str,
    field_data: List[Union[dict, FieldDefinition]],
    config=None
):
    """Create a new model from a given field set."""
    fields = {}

    for fdef in field_data:
        if type(fdef) == dict:
            fdef = FieldDefinition(**fdef)

        field = {}

        #
        # Documentation and validation
        #

        for k in [
            # Descriptive tags
            "title", "description", "example",
            # Numeric validators
            "gt", "ge", "lt", "le",
            # String validators
            "min_length", "max_length", "regex"
        ]:
            if getattr(fdef, k):
                field[k] = getattr(fdef, k)
        #
        # Default value
        #

        if fdef.submodel:
            field["default_factory"] = fdef.submodel
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
        elif fdef.type in FIELD_TYPES:
            ftype = FIELD_TYPES[fdef.type]
        else:
            ftype = Any

        fields[fdef.name] = (ftype, Field(**field))

    return create_model(
        model_name,
        __config__=config,
        **fields
    )
