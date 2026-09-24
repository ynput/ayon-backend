"""Helpers for working with pydantic field definitions."""

import types
from collections.abc import Iterator, Mapping, Sequence
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic.fields import FieldInfo
from pydantic_core import PydanticSerializationError, to_jsonable_python

from ayon_server.models.dynamic_model import get_dynamic_model

NoneType = type(None)


class FieldExtra:
    """Custom (AYON specific) extra attributes of a field.

    Used as `json_schema_extra` of a field. Unlike a plain dict,
    it may contain values that cannot be serialized to JSON
    (such as enum resolver functions). Such values are available
    using `get_field_extra`, but they are not included in the JSON schema.
    """

    def __init__(self, extra: dict[str, Any]) -> None:
        self.extra = extra

    def __call__(self, json_schema: dict[str, Any]) -> None:
        for key, value in self.extra.items():
            try:
                json_schema[key] = to_jsonable_python(value)
            except PydanticSerializationError:
                continue

    def __repr__(self) -> str:
        return f"FieldExtra({self.extra!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FieldExtra) and other.extra == self.extra


def get_field_extra(field: FieldInfo | None) -> dict[str, Any]:
    """Return custom (AYON specific) extra attributes of a field.

    Pydantic 1 stored unknown Field kwargs in `field_info.extra`.
    In Pydantic 2 they live in `json_schema_extra`, which is what
    SettingsField and RestField use.
    """
    if field is None:
        return {}
    extra = field.json_schema_extra
    if isinstance(extra, FieldExtra):
        return extra.extra
    if isinstance(extra, dict):
        return extra
    return {}


class V1FieldInfo:
    """Pydantic 1 style view of a field definition.

    Provides the `extra` attribute (custom field arguments),
    everything else is taken from the Pydantic 2 FieldInfo.
    """

    def __init__(self, field_info: FieldInfo) -> None:
        self._field_info = field_info

    @property
    def extra(self) -> dict[str, Any]:
        return get_field_extra(self._field_info)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._field_info, name)


class V1ModelField:
    """Pydantic 1 style view of a model field (ModelField).

    Used for backwards compatibility with addons accessing
    `SettingsModel.__fields__`.
    """

    def __init__(self, name: str, field_info: FieldInfo) -> None:
        self.name = name
        self.field_info = V1FieldInfo(field_info)
        self.alias = field_info.alias or name
        self.annotation = field_info.annotation
        self.outer_type_ = strip_optional(field_info.annotation)
        self.type_ = get_inner_type(field_info.annotation)
        self.required = field_info.is_required()
        self.default_factory = field_info.default_factory
        self.default = None
        if not self.required and field_info.default_factory is None:
            self.default = field_info.default
        self.allow_none = is_optional_annotation(field_info.annotation)

    def get_default(self) -> Any:
        return self.field_info.get_default(call_default_factory=True)

    def __repr__(self) -> str:
        return f"ModelField(name={self.name!r}, type={self.outer_type_!r})"


def is_optional_annotation(annotation: Any) -> bool:
    """Return True if the annotation accepts None (or is Any)."""
    if annotation is Any or annotation is None or annotation is NoneType:
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        return is_optional_annotation(get_args(annotation)[0])
    if origin is Union or origin is types.UnionType:
        return any(is_optional_annotation(arg) for arg in get_args(annotation))
    return False


def strip_optional(annotation: Any) -> Any:
    """Remove Annotated and None from the annotation.

    `Optional[list[int]]` becomes `list[int]`. Unions of multiple
    non-None types are returned as they are (without None).
    Dynamic models are resolved to the current model class.
    """
    origin = get_origin(annotation)
    if origin is Annotated:
        if dynamic_model := get_dynamic_model(annotation):
            return dynamic_model.resolve()
        return strip_optional(get_args(annotation)[0])
    if origin is Union or origin is types.UnionType:
        args = [arg for arg in get_args(annotation) if arg is not NoneType]
        if len(args) == 1:
            return strip_optional(args[0])
        return Union[tuple(args)]  # noqa: UP007
    return annotation


def get_inner_type(annotation: Any) -> Any:
    """Return the innermost type of a field annotation.

    This is the equivalent of Pydantic 1 `ModelField.type_`:
    Optional, Annotated and containers (list, set, dict values...)
    are unwrapped, so `list[SomeModel] | None` returns `SomeModel`.
    """
    annotation = strip_optional(annotation)
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = get_args(annotation)
    if not args:
        return annotation
    if isinstance(origin, type):
        if issubclass(origin, Mapping):
            return get_inner_type(args[-1])
        if issubclass(origin, tuple):
            if len(args) == 2 and args[1] is Ellipsis:
                return get_inner_type(args[0])
            return annotation
        if issubclass(origin, Sequence | set | frozenset):
            return get_inner_type(args[0])
    return annotation


def get_field_annotation(field: FieldInfo) -> Any:
    """Return the annotation of a field.

    For dynamic model fields, the current model class is returned.
    """
    if dynamic_model := get_dynamic_model(field):
        return dynamic_model.resolve()
    return field.annotation


def iter_annotation_types(annotation: Any) -> Iterator[Any]:
    """Yield the annotation and all types nested in it (recursively)."""
    if dynamic_model := get_dynamic_model(annotation):
        yield dynamic_model.resolve()
        return
    yield annotation
    for arg in get_args(annotation):
        if arg is Ellipsis or isinstance(arg, str | int | float | bool):
            continue  # Literal values, tuple ellipsis
        yield from iter_annotation_types(arg)


def format_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Make validation error details safe to send to the client.

    Removes the submitted values (`input`, which may contain secrets)
    and documentation links (`url`) and converts the context to JSON
    serializable values (it may contain exception objects).
    """
    result = []
    for error in errors:
        item = {k: v for k, v in dict(error).items() if k not in ("input", "url")}
        if "ctx" in item and isinstance(item["ctx"], dict):
            ctx = {}
            for key, value in item["ctx"].items():
                try:
                    ctx[key] = to_jsonable_python(value)
                except PydanticSerializationError:
                    ctx[key] = str(value)
            item["ctx"] = ctx
        result.append(item)
    return result
