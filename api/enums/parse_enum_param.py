from datetime import datetime
from typing import Any, Literal, NoReturn, overload

from ayon_server.exceptions import BadRequestException
from ayon_server.types import AttributeType


@overload
def parse_enum_param(
    param_type: Literal["string"],
    raw_value: str,
) -> str: ...


@overload
def parse_enum_param(
    param_type: Literal["integer"],
    raw_value: str,
) -> int: ...


@overload
def parse_enum_param(
    param_type: Literal["float"],
    raw_value: str,
) -> float: ...


@overload
def parse_enum_param(
    param_type: Literal["boolean"],
    raw_value: str,
) -> bool: ...


@overload
def parse_enum_param(
    param_type: Literal["datetime"],
    raw_value: str,
) -> datetime: ...


@overload
def parse_enum_param(
    param_type: Literal["list_of_strings"],
    raw_value: str,
) -> list[str]: ...


@overload
def parse_enum_param(
    param_type: Literal["list_of_integers"],
    raw_value: str,
) -> list[int]: ...


@overload
def parse_enum_param(
    param_type: Literal["list_of_any"] | Literal["list_of_submodels"] | Literal["dict"],
    raw_value: str,
) -> NoReturn: ...


def parse_enum_param(param_type: AttributeType, raw_value: str) -> Any:
    """Parse a query parameter value based on its expected type."""
    if param_type == "boolean":
        return raw_value.lower() in ("1", "true", "yes", "on")
    if param_type == "integer":
        return int(raw_value)
    if param_type == "float":
        return float(raw_value)
    if param_type == "list_of_strings":
        return [r.strip() for r in raw_value.split(",")]
    if param_type == "list_of_integers":
        return [int(r.strip()) for r in raw_value.split(",")]
    if param_type == "string":
        return raw_value
    if param_type == "datetime":
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            raise BadRequestException(f"Invalid datetime format: {raw_value}")
    raise BadRequestException(f"Unsupported parameter type: {param_type}")
