"""Pydantic 1 compatibility layer for addons.

Addon code importing `pydantic` (e.g. `from pydantic import Field, validator`)
receives this module instead (see `ayon_server.helpers.modules`).
It exposes everything from Pydantic 2 and overrides the few Pydantic 1
APIs addon settings rely on, that would otherwise fail in Pydantic 2:

- `Field` accepts Pydantic 1 arguments (regex, min_items, max_items, const...)
  and stores unknown arguments (widget, section, enum_resolver...)
  in json_schema_extra, the same way SettingsField does.
- `validator` supports the `field` and `config` arguments.
- `root_validator` does not require `skip_on_failure=True`
  for post-validators.

The rest of the Pydantic 1 API is provided by Pydantic 2
itself (deprecated, but functional).
"""

import dataclasses
import inspect
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pydantic as _pydantic
from pydantic_core import PydanticUndefined, core_schema

from ayon_server.models.field_info import (
    FieldExtra,
    V1ModelField,
    translate_field_kwargs,
)

__all__ = list(_pydantic.__all__)

# Arguments of Pydantic 2 Field and the Pydantic 1 arguments translated
# by translate_field_kwargs. Everything else is stored in the extra.
_FIELD_PARAMS = set(inspect.signature(_pydantic.Field).parameters) | {
    "regex",
    "min_items",
    "max_items",
    "allow_mutation",
    "unique_items",
    "const",
    "example",
}


def Field(default: Any = PydanticUndefined, **kwargs: Any) -> Any:
    """Pydantic 1 compatible Field"""

    # Pydantic 1 stored unknown arguments in the field extra
    unknown = {k: kwargs.pop(k) for k in list(kwargs) if k not in _FIELD_PARAMS}
    kwargs, extra = translate_field_kwargs(default, kwargs)
    extra.update(unknown)

    if extra:
        json_schema_extra = kwargs.get("json_schema_extra")
        if isinstance(json_schema_extra, dict):
            extra = {**json_schema_extra, **extra}
        if json_schema_extra is None or isinstance(json_schema_extra, dict):
            kwargs["json_schema_extra"] = FieldExtra(extra)

    return _pydantic.Field(default, **kwargs)


def _make_v1_field_validator(
    validator: Callable[..., Any],
) -> core_schema.WithInfoValidatorFunction:
    """Pydantic 2 shim for Pydantic 1 validators with field/config args.

    `validator` is the classmethod bound to the model class.
    """
    model = getattr(validator, "__self__", None)
    params = inspect.signature(validator).parameters
    has_var_kw = any(p.kind is p.VAR_KEYWORD for p in params.values())

    def wrapper(value: Any, info: core_schema.ValidationInfo) -> Any:
        kwargs: dict[str, Any] = {}
        if has_var_kw or "values" in params:
            kwargs["values"] = info.data
        if (has_var_kw or "field" in params) and model and info.field_name:
            field_info = model.model_fields[info.field_name]
            kwargs["field"] = V1ModelField(info.field_name, field_info)
        if has_var_kw or "config" in params:
            kwargs["config"] = SimpleNamespace(**(model.model_config if model else {}))
        return validator(value, **kwargs)

    return wrapper


def validator(
    __field: str,
    *fields: str,
    pre: bool = False,
    each_item: bool = False,
    always: bool = False,
    check_fields: bool | None = None,
    allow_reuse: bool = False,
) -> Any:
    """Pydantic 1 compatible validator

    Pydantic 2 provides a deprecated `validator`, which however
    does not support the `field` and `config` arguments.
    """

    pydantic_dec = _pydantic.validator(
        __field,
        *fields,
        pre=pre,
        each_item=each_item,
        always=always,
        check_fields=check_fields,
        allow_reuse=allow_reuse,
    )

    def dec(f: Any) -> Any:
        func = f.__func__ if isinstance(f, classmethod | staticmethod) else f
        params = inspect.signature(func).parameters
        proxy = pydantic_dec(f)
        if "field" in params or "config" in params:
            proxy = dataclasses.replace(proxy, shim=_make_v1_field_validator)
        return proxy

    return dec


def root_validator(
    *args: Any,
    pre: bool = False,
    skip_on_failure: bool = False,
    allow_reuse: bool = False,
) -> Any:
    """Pydantic 1 compatible root_validator

    Pydantic 2 refuses post root validators without skip_on_failure=True.
    """
    if args:
        return root_validator()(*args)
    return _pydantic.root_validator(  # type: ignore[call-overload]
        pre=pre,
        skip_on_failure=skip_on_failure or not pre,
        allow_reuse=allow_reuse,
    )


def __getattr__(name: str) -> Any:
    return getattr(_pydantic, name)


def __dir__() -> list[str]:
    return sorted(set(dir(_pydantic)) | set(globals()))
