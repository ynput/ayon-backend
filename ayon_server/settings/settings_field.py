import traceback
from collections.abc import Callable
from typing import Any

from pydantic import Field
from pydantic_core import PydanticUndefined

from ayon_server.logging import logger
from ayon_server.models.field_info import FieldExtra

"""
Unused pydantic fields
    exclude: Optional[Union['AbstractSetIntStr', 'MappingIntStrAny', Any]] = None,
    include: Optional[Union['AbstractSetIntStr', 'MappingIntStrAny', Any]] = None,
    const: Optional[bool] = None,
"""


def SettingsField(
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
    # AYON settings specifics
    example: Any = None,
    enum_resolver: Callable[..., Any] | str | None = None,
    enum_resolver_settings: dict[str, Any] | None = None,
    required_items: list[str] | None = None,
    section: str | None = None,
    widget: str | None = None,
    syntax: str | None = None,
    layout: str | None = None,
    tags: list[str] | None = None,
    scope: list[str] | None = None,
    placeholder: str | None = None,
    conditional_enum: bool = False,
    disabled: bool = False,
    # compatibility
    conditionalEnum: bool = False,  # backward compatibility
    examples: list[Any] | None = None,
    # everything else
    **kwargs: Any,
) -> Any:
    """Define a field of a settings model.

    Accepts both the Pydantic 1 (regex, min_items...) and the
    Pydantic 2 (pattern, min_length...) style arguments.

    AYON specific arguments are stored in the field's `json_schema_extra`
    (use `ayon_server.models.field_info.get_field_extra` to read them)
    and (if they are JSON serializable) exposed in the settings JSON schema
    the same way Pydantic 1 exposed extra field arguments.
    """

    # conditionalEnum (camelCase) is deprecated, but used heavily.
    # We will need to support it for a long time, but it won't hurt.
    conditional_enum = conditional_enum or conditionalEnum
    if conditionalEnum:
        stack = traceback.extract_stack()[-2]
        logger.debug(
            f"Deprecated argument: conditionalEnum at {stack.filename}:{stack.lineno}"
        )

    if kwargs:
        stack = traceback.extract_stack()[-2]
        logger.debug(
            f"Unsupported argument: {', '.join(kwargs.keys())} "
            f"at {stack.filename}:{stack.lineno}"
        )

    examples = list(examples or [])
    if example is not None:
        examples.append(example)

    # extras

    extra: dict[str, Any] = {}

    if unique_items:
        extra["uniqueItems"] = True
    if enum_resolver is not None:
        extra["enum_resolver"] = enum_resolver
    if enum_resolver_settings is not None:
        extra["enum_resolver_settings"] = enum_resolver_settings
    if required_items is not None:
        extra["required_items"] = required_items
    if section is not None:
        extra["section"] = section
    if widget is not None:
        extra["widget"] = widget
    if layout is not None:
        extra["layout"] = layout
    if tags is not None:
        extra["tags"] = tags
    if placeholder is not None:
        extra["placeholder"] = placeholder
    if conditional_enum:
        extra["conditional_enum"] = conditional_enum
    if scope is not None:
        extra["scope"] = scope
    if disabled is not None:
        extra["disabled"] = disabled
    if syntax is not None:
        if widget != "textarea":
            m = "SettingsField: syntax is only supported for textarea widget"
            logger.debug(m)
        extra["syntax"] = syntax.lower()

    # construct FieldInfo

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
        "json_schema_extra": FieldExtra(extra),
    }
    return Field(default, **field_kwargs)
