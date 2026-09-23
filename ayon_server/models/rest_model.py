from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticUndefined

from ayon_server.logging import logger
from ayon_server.models.metaclass import AyonModelMetaclass, coerce_v1_input
from ayon_server.utils import camelize


class RestModel(BaseModel, metaclass=AyonModelMetaclass):
    """Base API model."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        validate_by_alias=True,
        alias_generator=camelize,
        # Pydantic 1 accepted numbers for string fields
        coerce_numbers_to_str=True,
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_v1_input(cls, data: Any) -> Any:
        return coerce_v1_input(cls, data)


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

    examples = list(examples or [])
    if example is not None:
        examples.append(example)

    extra: dict[str, Any] = {}
    if unique_items:
        extra["uniqueItems"] = True
    if deprecated:
        # Only mark the field as deprecated in the schema.
        # Using pydantic's `deprecated` would emit runtime warnings
        # each time the attribute is accessed.
        extra["deprecated"] = True

    field_kwargs: dict[str, Any] = {
        "default_factory": default_factory,
        "alias": alias,
        "title": title,
        "description": description,
        "examples": examples or None,
        "gt": gt,
        "ge": ge,
        "lt": lt,
        "le": le,
        "multiple_of": multiple_of,
        "allow_inf_nan": allow_inf_nan,
        "max_digits": max_digits,
        "decimal_places": decimal_places,
        "min_length": min_length if min_length is not None else min_items,
        "max_length": max_length if max_length is not None else max_items,
        "frozen": None if allow_mutation else True,
        "pattern": pattern or regex,
        "discriminator": discriminator,
        "repr": repr,
        "validate_default": validate_default,
        "json_schema_extra": extra or None,
    }
    return Field(default, **field_kwargs)
