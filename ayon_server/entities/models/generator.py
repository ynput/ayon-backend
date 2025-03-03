"""Model generator.

Warning! We need to use typing.List in the models,
since Python 3.10 syntax does not work with Strawberry yet.
"""

import uuid
from datetime import datetime
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel, Field, create_model

from ayon_server.logging import log_traceback
from ayon_server.types import AttributeEnumItem, AttributeType

C = TypeVar("C", bound=type)

T = TypeVar("T", bound=BaseModel)


def get_list_ftype(submodel: type[T]) -> type[list[T]]:
    return list[T]


#
# Field types
#


FIELD_TYPES = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "datetime": datetime,
    "list_of_strings": list[str],
    "list_of_integers": list[int],
    "list_of_any": list[Any],
    "list_of_submodels": list[Any],
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


class FieldDefinition(BaseModel):
    """Field definition model."""

    # Required
    name: str = Field(title="Name of the field")
    required: bool = Field(title="Required field", default=False)

    type: AttributeType = Field(default="string", title="Field data type")
    submodel: Any | None
    list_of_submodels: Any | None
    # Descriptive
    title: str | None = Field(title="Nice field title")
    description: str | None = Field(title="Field description")
    example: Any | None = Field(title="Field example")

    # Default value
    default: Any | None = Field(title="Field default value")
    factory: Literal["list", "dict", "now", "uuid", "time"] | None = Field(
        title="Default factory",
        description="Name of the function to be used to create default values",
    )

    # Validation
    gt: int | float | None = Field(title="Greater than")
    ge: int | float | None = Field(title="Geater or equal")
    lt: int | float | None = Field(title="Less")
    le: int | float | None = Field(title="Less or equal")
    min_length: int | None = Field(title="Minimum length")
    max_length: int | None = Field(title="Maximum length")
    min_items: int | None = Field(title="Minimum items")
    max_items: int | None = Field(title="Maximum items")
    regex: str | None = Field(title="Field regex")
    enum: list[AttributeEnumItem] | None = Field(None, title="Enum values")


def generate_model(
    model_name: str,
    field_data: list[dict[str, Any]],
    config: C | None = None,
) -> type[BaseModel]:
    """Create a new model from a given field set."""
    fields = {}

    for fdef_data in field_data:
        try:
            fdef = FieldDefinition(**fdef_data)
        except Exception:
            log_traceback(
                f"Unable to load attribute '{fdef_data.get('name', 'Unknown')}'"
            )

            continue

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

        if field.get("enum"):
            field["_attrib_enum"] = True
            if isinstance(field["enum"][0], AttributeEnumItem):
                field["enum"] = [e.value for e in field["enum"]]
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

        ftype: Any

        if fdef.submodel:
            ftype = cast(type, fdef.submodel)
        elif fdef.list_of_submodels:
            assert fdef.list_of_submodels

            # fdef.list_of_submodels could be either a subclass
            # of pydantic.BaseModel or a callable that returns a subclass
            # of pydantic.BaseModel

            submodel: type[BaseModel]

            if isinstance(fdef.list_of_submodels, type) and issubclass(
                fdef.list_of_submodels, BaseModel
            ):
                submodel = fdef.list_of_submodels
                ftype = get_list_ftype(submodel)
            elif callable(fdef.list_of_submodels):
                submodel = cast(type[BaseModel], fdef.list_of_submodels())
                ftype = get_list_ftype(submodel)

        elif fdef.type in FIELD_TYPES:
            if fdef.required:
                ftype = FIELD_TYPES[fdef.type]
            else:
                ftype = FIELD_TYPES[fdef.type] | None
        else:
            ftype = Any

        fields[fdef.name] = (ftype, Field(**field))  # type: ignore

    return create_model(model_name, __config__=config, **fields)  # type: ignore
