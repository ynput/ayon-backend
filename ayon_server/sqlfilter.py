import json
import re
from typing import Annotated, Any, Literal, Union

from pydantic import StrictFloat, StrictInt, StrictStr, validator

from ayon_server.logging import logger
from ayon_server.types import Field, OPModel

ValueType = (
    StrictStr
    | StrictInt
    | StrictFloat
    | list[StrictStr]
    | list[StrictInt]
    | list[StrictFloat]
    | None
)


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
    "excludesany",
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
    def validate_value(cls, v: ValueType, values: dict[str, Any]):
        logger.trace(f"Validating {type(v)} value {v} with {values}")
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


PATH_ELEMENT_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def create_path_from_key(
    key: str,
    column_whitelist: list[str] | None = None,
) -> list[str]:
    """Ensure the key is valid and return a list of path elements.

    That means the key must be a valid path separated by slashes or dots.
    First element must be a valid column name (converted to snake_case).
    All elements must conform to the PATH_ELEMENT_REGEX.
    """
    key = key.replace("/", ".")
    path = [k.strip() for k in key.split(".")]
    if not path:
        raise ValueError("Empty path")
    if not all(PATH_ELEMENT_REGEX.match(p) for p in path):
        raise ValueError("Invalid path element detected")

    # First element (column) must be snake_case
    column = camel_to_snake(path[0])
    if column_whitelist is not None and column not in column_whitelist:
        raise ValueError(f"Invalid key: {column}")
    path[0] = column
    return path


def build_condition(c: QueryCondition, **kwargs) -> str:
    """Return a SQL WHERE clause from a Condition object."""

    json_fields = kwargs.get("json_fields", JSON_FIELDS)
    table_prefix = kwargs.get("table_prefix")
    column_whitelist = kwargs.get("column_whitelist", None)
    column_map: dict[str, str] = kwargs.get("column_map", {})

    path = create_path_from_key(c.key, column_whitelist)
    value = c.value
    operator = c.operator
    cast_type = "text"
    safe_value: ValueType = None

    column = path[0]
    if column in column_map:
        column = column_map[column]

    if len(path) == 1 and path[0] not in json_fields:
        # Hack to map project and user to their respective db column names
        # when querying from the events table
        if column in ["project", "user"]:
            column = f"{column}_name"

        if isinstance(value, str):
            safe_value = value.replace("'", "''")
            safe_value = f"'{value}'"

        elif isinstance(value, int | float):
            cast_type = "integer" if isinstance(value, int) else "number"
            safe_value = value

    elif len(path) > 1 and path[0] in json_fields:
        for k in path[1:]:
            column += f"->'{k}'"

        if isinstance(value, str | int | float):
            safe_value = json.dumps(value).replace("'", "''")
            safe_value = f"'{safe_value}'"
            logger.trace(f"Safe value of {type(value)} {value}: {safe_value}")

    else:
        raise ValueError(f"Invalid path: {path}")

    if table_prefix and path[0] not in column_map:
        column = f"{table_prefix}.{column}"

    if isinstance(value, list):
        if len(value) == 0:
            if operator == "eq":
                return f"array_length({column}, 1) IS NULL"
            if operator == "ne":
                return f"array_length({column}, 1) IS NOT NULL"

        if all(isinstance(v, str) for v in value):
            escaped_list = [v.replace("'", "''") for v in value]  # type: ignore
            if len(path) > 1:
                # crawling a json, so we need to quote the values
                arr_value = (
                    "array[" + ", ".join([f"'\"{v}\"'" for v in escaped_list]) + "]"
                )
            else:
                arr_value = "array[" + ", ".join([f"'{v}'" for v in escaped_list]) + "]"
        elif all(isinstance(v, (int)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "integer"
        elif all(isinstance(v, (float)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "number"
        else:
            raise ValueError("Invalid value type in list")

        if operator == "contains":
            return f"({column})::{cast_type}[] @> {arr_value}"
        elif operator == "excludesany":
            return f"NOT (({column})::{cast_type}[] @> {arr_value})"
        elif operator == "excludes":
            return f"NOT(({column})::{cast_type}[] && {arr_value})"
        elif operator == "any":
            return f"({column})::{cast_type}[] && {arr_value}"

        elif operator == "in":
            return f"({column})::{cast_type} = ANY({arr_value})"
        elif operator == "notin":
            return f"NOT ({column})::{cast_type} = ANY({arr_value})"

        else:
            raise ValueError(f"Invalid list operator: {operator}")

    if operator == "isnull":
        return f"{column} IS NULL"
    elif operator == "notnull":
        return f"{column} IS NOT NULL"

    if safe_value is None:
        raise ValueError(f"Invalid value: {value}")

    if operator == "eq":
        return f"{column} = {safe_value}"
    elif operator == "lt":
        return f"{column} < {safe_value}"
    elif operator == "gt":
        return f"{column} > {safe_value}"
    elif operator == "lte":
        return f"{column} <= {safe_value}"
    elif operator == "gte":
        return f"{column} >= {safe_value}"
    elif operator == "ne":
        return f"{column} != {safe_value}"
    elif operator == "contains":
        return f"{safe_value} = ANY({column})"
    elif operator == "excludes":
        return f"NOT ({safe_value} = ANY({column}))"
    elif operator == "like":
        return f"{column} LIKE {safe_value}"
    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_filter(f: QueryFilter | None, **kwargs) -> str | None:
    """Return a SQL WHERE clause from a Filter object."""

    if f is None:
        return None

    if not f.conditions:
        logger.trace(f"Empty conditions {f.dict()}")
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
