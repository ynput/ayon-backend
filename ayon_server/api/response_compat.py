"""Backwards compatible response serialization.

With Pydantic 1, FastAPI serialized responses of endpoints
with a response model (or a return type annotation) as follows:

1. Returned models were converted to dicts
2. The data was validated against the response model
3. The result was encoded using `jsonable_encoder`

Current FastAPI validates the returned object directly and
encodes it using Pydantic 2. That:

- breaks endpoints declared to return a dict, but returning a model
  (common in addons returning settings)
- changes the responses of endpoints relying on the re-validation
  (validators and defaults applied to the response data)
- changes `exclude_none` to affect only model fields, not dict values
- changes the format of some values (e.g. UTC datetimes are encoded
  as `...Z` instead of `...+00:00`, which `datetime.fromisoformat`
  cannot parse before Python 3.11, still used by some DCC applications)

We keep the original behavior, but encode the data using orjson,
which produces the same output as `jsonable_encoder` for common types,
but is considerably faster.
"""

import dataclasses
from typing import Any

import fastapi.routing
import orjson
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import EndpointContext, ResponseValidationError
from pydantic import BaseModel

_serialize_response = fastapi.routing.serialize_response

ORJSON_OPTIONS = orjson.OPT_NON_STR_KEYS | orjson.OPT_PASSTHROUGH_DATACLASS


def _prepare_response_content(
    res: Any,
    *,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
) -> Any:
    kwargs = {
        "exclude_unset": exclude_unset,
        "exclude_defaults": exclude_defaults,
        "exclude_none": exclude_none,
    }
    if isinstance(res, BaseModel):
        return res.model_dump(
            by_alias=True,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
    if isinstance(res, list):
        return [_prepare_response_content(item, **kwargs) for item in res]
    if isinstance(res, dict):
        return {k: _prepare_response_content(v, **kwargs) for k, v in res.items()}
    if dataclasses.is_dataclass(res) and not isinstance(res, type):
        return dataclasses.asdict(res)
    return res


def _drop_none(data: Any) -> Any:
    """Recursively remove None values from dicts.

    `jsonable_encoder(..., exclude_none=True)` also dropped None values
    of plain dicts (e.g. `data` fields), not only model fields.
    """
    if isinstance(data, dict):
        return {k: _drop_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [_drop_none(v) for v in data]
    return data


def _default(value: Any) -> Any:
    return jsonable_encoder(value)


async def serialize_response(
    *,
    field: Any = None,
    response_content: Any,
    include: Any = None,
    exclude: Any = None,
    by_alias: bool = True,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    is_coroutine: bool = True,
    endpoint_ctx: EndpointContext | None = None,
    dump_json: bool = False,
) -> Any:
    if field is None:
        return await _serialize_response(
            response_content=response_content,
            endpoint_ctx=endpoint_ctx,
            dump_json=dump_json,
        )

    prepared = _prepare_response_content(
        response_content,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        exclude_none=exclude_none,
    )

    if is_coroutine:
        value, errors = field.validate(prepared, {}, loc=("response",))
    else:
        value, errors = await run_in_threadpool(
            field.validate, prepared, {}, loc=("response",)
        )
    if errors:
        raise ResponseValidationError(
            errors=errors,
            body=prepared,
            endpoint_ctx=endpoint_ctx or EndpointContext(),
        )

    data = field.serialize(
        value,
        mode="python",
        include=include,
        exclude=exclude,
        by_alias=by_alias,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        exclude_none=exclude_none,
    )
    if exclude_none:
        data = _drop_none(data)

    if dump_json:
        return orjson.dumps(data, default=_default, option=ORJSON_OPTIONS)
    return jsonable_encoder(data)


def install() -> None:
    fastapi.routing.serialize_response = serialize_response
