import json
import re
from typing import Annotated, Literal, Union

from pydantic import validator

from ayon_server.types import Field, OPModel

ValueType = Union[str, int, float, list[str], list[int], list[float], None]
OperatorType = Literal[
    "eq",
    "lt",
    "gt",
    "lte",
    "gte",
    "ne",
    "isnull",
    "notnull",
    "in",
    "notin",
    "contains",
    "excludes",
    "any",
    "like",
]


def camel_to_snake(name):
    """Convert camelCase or PascalCase to snake_case."""
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return name


class QueryCondition(OPModel):
    key: Annotated[
        str,
        Field(
            title="Key",
            description="Path to the key separated by slashes",
            example="summary/newValue",
        ),
    ]
    value: Annotated[
        ValueType,
        Field(
            title="Value",
            description="Value to compare against",
            example="New value",
        ),
    ] = None
    operator: Annotated[
        OperatorType,
        Field(
            title="Operator",
            description="Comparison operator",
            example="eq",
        ),
    ] = "eq"

    @validator("operator", pre=True, always=True)
    def convert_operator_to_lowercase(cls, v):
        return v.lower()

    @validator("value")
    def validate_value(cls, v, values):
        if values.get("operator") in ("in", "notin", "any"):
            if not isinstance(v, list):
                raise ValueError("Value must be a list")
        if values.get("operator") not in ("isnull", "notnull"):
            if v is None:
                raise ValueError("Value cannot be null")
        return v


class QueryFilter(OPModel):
    conditions: Annotated[
        list[Union[QueryCondition, "QueryFilter"]],
        Field(
            default_factory=list,
            title="Conditions",
            description="List of conditions to be evaluated",
        ),
    ]
    operator: Annotated[
        Literal["and", "or"],
        Field(
            title="Operator",
            description="Operator to use when joining conditions",
        ),
    ] = "and"

    @validator("operator", pre=True, always=True)
    def convert_operator_to_lowercase(cls, v):
        return v.lower()


JSON_FIELDS = [
    "summary",
    "payload",
    "attrib",
    "data",
    "config",
]


def build_condition(c: QueryCondition, **kwargs) -> str:
    """Return a SQL WHERE clause from a Condition object."""

    pex = c.key.replace("/", ".")
    path = [k.strip() for k in pex.split(".")]
    value = c.value
    operator = c.operator
    cast_type = "text"
    assert path, "Path cannot be empty"

    json_fields = kwargs.get("json_fields", JSON_FIELDS)
    table_prefix = kwargs.get("table_prefix")
    key_whitelist = kwargs.get("key_whitelist", None)

    key = path[0]
    key = camel_to_snake(key)
    if key_whitelist is not None:
        if key not in key_whitelist:
            raise ValueError(f"Invalid key: {key}")

    if len(path) == 1 and path[0] not in json_fields:
        # Hack to map project and user to their respective db column names
        if key in ["project", "user"]:
            key = f"{key}_name"

        if isinstance(value, str):
            value = value.replace("'", "''")
            value = f"'{value}'"
        elif isinstance(value, (int, float)):
            cast_type = "integer" if isinstance(value, int) else "number"

    elif len(path) > 1 and key in json_fields:
        for k in path[1:]:
            key += f"->'{k}'"

        if isinstance(value, (str, int, float)):
            if isinstance(value, str):
                value = value.replace("'", "''")
            value = f"'{json.dumps(value)}'"

    else:
        raise ValueError(f"Invalid path: {path}")

    if table_prefix:
        key = f"{table_prefix}.{key}"

    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            value = [v.replace("'", "''") for v in value]  # type: ignore
            arr_value = "array[" + ", ".join([f"'{v}'" for v in value]) + "]"
        elif all(isinstance(v, (int)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "integer"
        elif all(isinstance(v, (float)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "number"
        else:
            raise ValueError("Invalid value type in list")

        if operator == "in":
            if len(path) > 1:
                return f"{key}::{cast_type} ?| {arr_value}"
            else:
                return f"{key}::{cast_type} = ANY({arr_value})"
        elif operator == "notin":
            if len(path) > 1:
                return f"NOT ({key}::{cast_type} ?| {arr_value})"
            else:
                return f"{key}::{cast_type} != ALL({arr_value})"
        elif operator == "any":
            return f"{key}::{cast_type}[] && {arr_value}"
        else:
            raise ValueError(f"Invalid list operator: {operator}")

    if operator == "isnull":
        return f"{key} IS NULL"
    elif operator == "notnull":
        return f"{key} IS NOT NULL"
    elif operator == "eq":
        return f"{key} = {value}"
    elif operator == "lt":
        return f"{key} < {value}"
    elif operator == "gt":
        return f"{key} > {value}"
    elif operator == "lte":
        return f"{key} <= {value}"
    elif operator == "gte":
        return f"{key} >= {value}"
    elif operator == "ne":
        return f"{key} != {value}"
    elif operator == "contains":
        return f"{key} @> {value}"
    elif operator == "excludes":
        return f"NOT ({key} @> {value})"
    elif operator == "like":
        return f"{key} LIKE {value}"
    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_filter(f: QueryFilter | None, **kwargs) -> str | None:
    """Return a SQL WHERE clause from a Filter object."""

    if f is None:
        return None

    if not f.conditions:
        return None

    result = []
    for c in f.conditions:
        if isinstance(c, QueryFilter):
            if r := build_filter(c, **kwargs):
                result.append(r)
        elif isinstance(c, QueryCondition):
            if r := build_condition(c, **kwargs):
                result.append(r)
        else:
            raise ValueError(f"Invalid condition: {c}")

    if not result:
        return None

    return f"({f' {f.operator.upper()} '.join(result)})"
