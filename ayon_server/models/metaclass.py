"""Pydantic 1 compatibility of AYON base models (RestModel, BaseSettingsModel)."""

import copy
import inspect
import sys
from typing import Annotated, Any, ClassVar, get_args, get_origin

from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from ayon_server.models.field_info import is_optional_annotation, strip_optional


def _resolve_annotation(annotation: Any, namespace: dict[str, Any]) -> Any:
    if not isinstance(annotation, str):
        return annotation
    module = sys.modules.get(namespace.get("__module__", ""))
    globalns = dict(vars(module)) if module else {}
    try:
        return eval(annotation, globalns, dict(namespace))
    except Exception:
        # Unresolvable forward reference. Use a simple heuristic
        text = annotation.replace(" ", "")
        if text.startswith("Optional[") or "|None" in text or "None|" in text:
            return Any
        return annotation


def _annotated_has_default(annotation: Any) -> bool:
    """Return True if Annotated metadata define a default value"""
    if get_origin(annotation) is not Annotated:
        return False
    for meta in get_args(annotation)[1:]:
        if isinstance(meta, FieldInfo) and (
            meta.default is not PydanticUndefined or meta.default_factory is not None
        ):
            return True
    return False


def _infer_annotation(value: Any) -> Any:
    """Infer the type of a non-annotated field from its default value"""
    if isinstance(value, FieldInfo):
        if value.default_factory is not None:
            try:
                value = value.default_factory()  # type: ignore[call-arg]
            except Exception:
                return Any
        else:
            value = value.default
    if value is None or value is PydanticUndefined or value is Ellipsis:
        return Any
    return type(value)


class AyonModelMetaclass(ModelMetaclass):
    """Keep the Pydantic 1 semantics of model fields.

    Settings and REST models are also defined by addons, which were
    written for Pydantic 1, so we keep the original behavior here:

    - A field that accepts None (or `Any`) without an explicit default
      is not required and defaults to None.
      (Pydantic 2 makes such fields required)
    - A field without a type annotation infers its type from its default value.
      (Pydantic 2 refuses non-annotated fields)
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ):
        annotations = namespace.setdefault("__annotations__", {})

        # Non-annotated fields

        for field_name, value in list(namespace.items()):
            if field_name.startswith("_") or field_name in annotations:
                continue
            if field_name == "model_config":
                continue
            if isinstance(value, type):
                # Nested classes (such as legacy Config) are not fields
                continue
            if inspect.isroutine(value) or hasattr(value, "__get__"):
                # methods, properties, validators...
                continue
            annotations[field_name] = _infer_annotation(value)

        # Optional fields without default

        for field_name, annotation in annotations.items():
            if field_name.startswith("_"):
                continue
            annotation = _resolve_annotation(annotation, namespace)
            if get_origin(annotation) is ClassVar:
                continue
            if not is_optional_annotation(annotation):
                continue
            if _annotated_has_default(annotation):
                continue
            value = namespace.get(field_name, PydanticUndefined)
            if value is PydanticUndefined:
                namespace[field_name] = None
            elif (
                isinstance(value, FieldInfo)
                and value.default is PydanticUndefined
                and value.default_factory is None
            ):
                namespace[field_name] = _with_default(value, None)
        return super().__new__(mcs, name, bases, namespace, **kwargs)


def _with_default(field_info: FieldInfo, default: Any) -> FieldInfo:
    result = copy.copy(field_info)
    result.default = default
    result._attributes_set = {**field_info._attributes_set, "default": default}
    return result


#
# Input coercion
#


def _field_coercions(model: type[BaseModel]) -> dict[str, str]:
    """Return names/aliases of fields needing Pydantic 1 style input coercion"""
    try:
        return model.__dict__["__ayon_field_coercions__"]
    except KeyError:
        pass

    result: dict[str, str] = {}
    for name, field in model.model_fields.items():
        annotation = strip_optional(field.annotation)
        origin = get_origin(annotation)
        args = get_args(annotation)
        if annotation is str:
            kind = "str"
        elif annotation is int:
            kind = "int"
        elif annotation is dict or origin is dict:
            kind = "dict"
        elif origin is list and args == (str,):
            kind = "list_str"
        elif (
            origin is list and args and (args[0] is dict or get_origin(args[0]) is dict)
        ):
            kind = "list_dict"
        else:
            continue
        result[name] = kind
        if field.alias:
            result[field.alias] = kind
    setattr(model, "__ayon_field_coercions__", result)
    return result


def coerce_v1_input(model: type[BaseModel], data: Any) -> Any:
    """Coerce input values the way Pydantic 1 did, where Pydantic 2 fails.

    - booleans are accepted by string fields ("True" / "False")
      (numbers are handled by the `coerce_numbers_to_str` config)
    - floats are accepted by integer fields (truncated)
    - models are accepted by dict fields (converted to dicts)

    Used by AyonBaseModel when the validation of the original data fails.
    """
    if not isinstance(data, dict):
        return data
    coercions = _field_coercions(model)
    if not coercions:
        return data

    result = None
    for key, kind in coercions.items():
        value = data.get(key)
        if value is None:
            continue
        new_value = value
        if kind == "str":
            if isinstance(value, bool):
                new_value = str(value)
        elif kind == "int":
            if isinstance(value, float) and not value.is_integer():
                new_value = int(value)
        elif kind == "list_str":
            if isinstance(value, list) and any(isinstance(v, bool) for v in value):
                new_value = [str(v) if isinstance(v, bool) else v for v in value]
        elif kind == "dict":
            if isinstance(value, BaseModel):
                new_value = dict(value)
        elif kind == "list_dict":
            if isinstance(value, list) and any(isinstance(v, BaseModel) for v in value):
                new_value = [dict(v) if isinstance(v, BaseModel) else v for v in value]
        if new_value is not value:
            if result is None:
                result = dict(data)
            result[key] = new_value
    return data if result is None else result
