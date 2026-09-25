from typing import Any, Unpack

from pydantic import ConfigDict, Field
from pydantic_core import PydanticUndefined

from ayon_server.models.base_model import AyonBaseModel
from ayon_server.models.field_info import (
    FieldExtra,
    FieldKwargs,
    known_field_kwargs,
    translate_field_kwargs,
)
from ayon_server.utils import camelize


class RestModel(AyonBaseModel):
    """Base API model."""

    model_config = ConfigDict(alias_generator=camelize)


def RestField(
    default: Any = PydanticUndefined,
    *,
    deprecated: bool = False,
    **kwargs: Unpack[FieldKwargs],
) -> Any:
    """Define a field of a RestModel.

    Accepts both the Pydantic 1 (regex, min_items...) and the
    Pydantic 2 (pattern, min_length...) style arguments.
    """

    field_kwargs, extra = translate_field_kwargs(
        default, known_field_kwargs("RestField", dict(kwargs))
    )

    if deprecated:
        # Only mark the field as deprecated in the schema.
        # Using pydantic's `deprecated` would emit runtime warnings
        # each time the attribute is accessed.
        extra["deprecated"] = True

    if extra:
        field_kwargs["json_schema_extra"] = FieldExtra(extra)
    return Field(default, **field_kwargs)
