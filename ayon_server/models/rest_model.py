from collections.abc import Callable
from typing import Any

from pydantic import ConfigDict, Field
from pydantic_core import PydanticUndefined

from ayon_server.logging import logger
from ayon_server.models.base_model import AyonBaseModel
from ayon_server.models.field_info import FieldExtra, translate_field_kwargs
from ayon_server.utils import camelize


class RestModel(AyonBaseModel):
    """Base API model."""

    model_config = ConfigDict(alias_generator=camelize)


def RestField(
    default: Any = PydanticUndefined,
    *,
    default_factory: Callable[[], Any] | None = None,
    alias: str | None = None,
    title: str | None = None,
    description: str | None = None,
    gt: float | None = None,
    ge: float | None = None,
    lt: float | None = None,
    le: float | None = None,
    multiple_of: float | None = None,
    allow_inf_nan: bool | None = None,
    max_digits: int | None = None,
    decimal_places: int | None = None,
    min_items: int | None = None,
    max_items: int | None = None,
    unique_items: bool | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    allow_mutation: bool = True,
    regex: str | None = None,
    pattern: str | None = None,
    discriminator: str | None = None,
    repr: bool = True,
    validate_default: bool | None = None,
    # AYON specifics
    example: Any = None,
    deprecated: bool = False,
    examples: list[Any] | None = None,
    # everything else
    **kwargs: Any,
) -> Any:
    """Define a field of a RestModel.

    Accepts both the Pydantic 1 (regex, min_items...) and the
    Pydantic 2 (pattern, min_length...) style arguments.
    """

    if kwargs:
        logger.debug(f"RestField: unsupported argument: {kwargs}")

    field_kwargs, extra = translate_field_kwargs(
        default,
        {
            "default_factory": default_factory,
            "alias": alias,
            "title": title,
            "description": description,
            "gt": gt,
            "ge": ge,
            "lt": lt,
            "le": le,
            "multiple_of": multiple_of,
            "allow_inf_nan": allow_inf_nan,
            "max_digits": max_digits,
            "decimal_places": decimal_places,
            "min_items": min_items,
            "max_items": max_items,
            "unique_items": unique_items,
            "min_length": min_length,
            "max_length": max_length,
            "allow_mutation": allow_mutation,
            "regex": regex,
            "pattern": pattern,
            "discriminator": discriminator,
            "repr": repr,
            "validate_default": validate_default,
            "example": example,
            "examples": examples,
        },
    )

    if deprecated:
        # Only mark the field as deprecated in the schema.
        # Using pydantic's `deprecated` would emit runtime warnings
        # each time the attribute is accessed.
        extra["deprecated"] = True

    if extra:
        field_kwargs["json_schema_extra"] = FieldExtra(extra)
    return Field(default, **field_kwargs)
