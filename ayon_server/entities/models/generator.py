"""Model generator.

Warning! We need to use typing.List in the models,
since Python 3.10 syntax does not work with Strawberry yet.
"""

import sys
import time
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PydanticUserError, create_model
from pydantic_core import SchemaError

from ayon_server.enum.enum_item import EnumItem
from ayon_server.logging import log_traceback, logger
from ayon_server.models.attrib_values import AttribValues
from ayon_server.types import AttributeType

#
# Field types
#


FIELD_TYPES: dict[AttributeType, type] = {
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
    submodel: Any | None = None
    list_of_submodels: Any | None = None
    # Descriptive
    title: str | None = Field(None, title="Nice field title")
    description: str | None = Field(None, title="Field description")
    example: Any | None = Field(None, title="Field example")

    # Default value
    default: Any | None = Field(None, title="Field default value")
    factory: Literal["list", "dict", "now", "uuid", "time"] | None = Field(
        None,
        title="Default factory",
        description="Name of the function to be used to create default values",
    )

    # Validation
    gt: int | float | None = Field(None, title="Greater than")
    ge: int | float | None = Field(None, title="Geater or equal")
    lt: int | float | None = Field(None, title="Less")
    le: int | float | None = Field(None, title="Less or equal")
    min_length: int | None = Field(None, title="Minimum length")
    max_length: int | None = Field(None, title="Maximum length")
    min_items: int | None = Field(None, title="Minimum items")
    max_items: int | None = Field(None, title="Maximum items")
    regex: str | None = Field(None, title="Field regex")
    enum: list[EnumItem] | None = Field(None, title="Enum values")


def attribute_field(fdef: FieldDefinition) -> tuple[Any, dict[str, Any]]:
    """Return the type and the Field arguments of an attribute."""
    field: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    #
    # Documentation and validation
    #

    for k in ("title", "description"):
        if getattr(fdef, k):
            field[k] = getattr(fdef, k)

    # Numeric and string validators (0 is a valid limit)
    for k in ("gt", "ge", "lt", "le", "min_length", "max_length"):
        if getattr(fdef, k) is not None:
            field[k] = getattr(fdef, k)

    if fdef.example:
        extra["example"] = fdef.example
    if fdef.regex:
        field["pattern"] = fdef.regex
    # Array validators
    if fdef.min_items is not None:
        field["min_length"] = fdef.min_items
    if fdef.max_items is not None:
        field["max_length"] = fdef.max_items

    # Enum
    if fdef.enum:
        extra["_attrib_enum"] = True
        extra["enum"] = [e.value for e in fdef.enum]
    if extra:
        field["json_schema_extra"] = extra

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

    if isinstance(fdef.submodel, AttribValues):
        ftype = fdef.submodel.annotation
    elif fdef.submodel:
        ftype = fdef.submodel
    elif fdef.list_of_submodels:
        assert fdef.list_of_submodels
        ftype = list[fdef.list_of_submodels]  # type: ignore
    elif fdef.type in FIELD_TYPES:
        if fdef.required:
            ftype = FIELD_TYPES[fdef.type]
        else:
            ftype = FIELD_TYPES[fdef.type] | None
    else:
        ftype = Any

    if "default" in field and "default_factory" in field:
        logger.error(
            f"Both default and default_factory provided for field '{fdef.name}'"
        )
        field.pop("default")

    return ftype, field


def attribute_test_model(
    fdef: FieldDefinition,
    ftype: Any,
    field: dict[str, Any],
    config: ConfigDict | None,
) -> type[BaseModel]:
    """Create a model with the attribute only, to check it can be constructed.

    The real field name is used, as some names are reserved by pydantic.
    Raises an exception when the attribute definition is not valid.
    """
    if hasattr(BaseModel, fdef.name):
        # e.g. model_config, model_dump or json (create_model would take
        # model_config as the model configuration instead of a field)
        raise ValueError(f"'{fdef.name}' is reserved and cannot be used")
    return create_model(  # type: ignore[call-overload]
        "test", __config__=config, **{fdef.name: (ftype, Field(**field))}
    )


def _test_field(
    fdef: FieldDefinition,
    ftype: Any,
    field: dict[str, Any],
    config: ConfigDict | None,
) -> None:
    """Ensure a stored attribute can be constructed.

    Pydantic 2 uses the Rust regex engine, which does not support
    look-around and backreferences, but attributes created before
    Pydantic 2 may use them. Such regex is removed from the field
    (the attribute is kept, but its values are not validated by the regex).
    New attributes with such regex are rejected (validate_attribute_data).
    """
    try:
        attribute_test_model(fdef, ftype, field, config)
    except SchemaError:
        if "pattern" not in field:
            raise
        logger.warning(
            f"Regex of attribute '{fdef.name}' is not supported "
            f"and it won't be validated: {fdef.regex}"
        )
        field.pop("pattern")
        attribute_test_model(fdef, ftype, field, config)


def generate_model(
    model_name: str,
    field_data: list[dict[str, Any]],
    config: ConfigDict | None = None,
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

        ftype, field = attribute_field(fdef)

        # ensure we can construct the model
        # (using the real field name, as some names are reserved by pydantic)
        try:
            _test_field(fdef, ftype, field, config)
        except (ValueError, TypeError, PydanticUserError, SchemaError):
            log_traceback(f"Unable to construct attribute '{fdef.name}'")
            continue

        fields[fdef.name] = (ftype, Field(**field))

    try:
        return create_model(model_name, __config__=config, **fields)  # type: ignore
    except ValueError:
        logger.error("Unable to start")
        log_traceback(f"Invalid attribute definition: {model_name}")
        time.sleep(5)
        sys.exit(1)
