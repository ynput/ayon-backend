from typing import Any, Literal, overload

from ayon_server.exceptions import BadRequestException
from ayon_server.types import AttributeType


@overload
def parse_enum_param(param_type: str, raw_value: Literal["string"]) -> str: ...


@overload
def parse_enum_param(param_type: str, raw_value: Literal["integer"]) -> int: ...


@overload
def parse_enum_param(param_type: str, raw_value: Literal["float"]) -> float: ...


@overload
def parse_enum_param(param_type: str, raw_value: Literal["boolean"]) -> bool: ...


@overload
def parse_enum_param(
    param_type: str, raw_value: Literal["list_of_strings"]
) -> list[str]: ...


@overload
def parse_enum_param(
    param_type: str, raw_value: Literal["list_of_integers"]
) -> list[int]: ...


@overload
def parse_enum_param(param_type: str, raw_value: AttributeType) -> Any: ...


def parse_enum_param(param_type: str, raw_value: AttributeType) -> Any:
    """Parse a query parameter value based on its expected type."""
    if param_type == "bool":
        return raw_value.lower() in ("1", "true", "yes", "on")
    if param_type == "int":
        return int(raw_value)
    if param_type == "float":
        return float(raw_value)
    if param_type == "list_of_strings":
        return [r.strip() for r in raw_value.split(",")]
    if param_type == "list_of_integers":
        return [int(r.strip()) for r in raw_value.split(",")]
    if param_type == "string":
        return raw_value
    raise BadRequestException(f"Unsupported parameter type: {param_type}")
