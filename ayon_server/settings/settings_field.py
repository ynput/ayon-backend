import warnings
from collections.abc import Callable
from typing import Any, Unpack

from pydantic import Field
from pydantic_core import PydanticUndefined

from ayon_server.deprecations import AyonDeprecationWarning
from ayon_server.logging import logger
from ayon_server.models.field_info import (
    FieldExtra,
    FieldKwargs,
    known_field_kwargs,
    translate_field_kwargs,
)


def SettingsField(
    default: Any = PydanticUndefined,
    *,
    # AYON settings specifics
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
    # standard field arguments
    **kwargs: Unpack[FieldKwargs],
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
        warnings.warn(
            "SettingsField: `conditionalEnum` is deprecated, "
            "use `conditional_enum` instead",
            AyonDeprecationWarning,
            stacklevel=2,
        )

    field_kwargs, extra = translate_field_kwargs(
        default, known_field_kwargs("SettingsField", dict(kwargs))
    )

    # AYON specific extras

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

    field_kwargs["json_schema_extra"] = FieldExtra(extra)
    return Field(default, **field_kwargs)
