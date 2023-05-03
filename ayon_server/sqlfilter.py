import json
from typing import Any, Literal, Union

from ayon_server.types import Field, OPModel


class Condition(OPModel):
    key: str = Field(
        ...,
        title="Key",
        description="Path to the key separated by slashes",
        example="summary/newValue",
    )
    value: Any = Field(
        ..., title="Value", description="Value to compare against", example="New value"
    )
    operator: Literal[
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
    ] = Field("eq")


class Filter(OPModel):
    conditions: list[Union[Condition, "Filter"]] = Field(default_factory=list)
    operator: Literal["and", "or"] = Field("and")


ROOT_FIELDS = [
    "topic",
    "project",
    "user",
    "depends_on",
    "status",
    "sender",
    "created_at",
    "updated_at",
]

JSON_FIELDS = [
    "summary",
    "payload",
    "attrib",
    "data",
]


def build_condition(c: Condition, **kwargs) -> str:
    """Return a SQL WHERE clause from a Condition object."""

    path = [k.strip() for k in c.key.split("/")]
    value = c.value
    operator = c.operator
    assert path, "Path cannot be empty"

    json_fields = kwargs.get("json_fields", JSON_FIELDS)
    normal_fields = kwargs.get("normal_fields", ROOT_FIELDS)
    table_prefix = kwargs.get("table_prefix", "source_events")

    key = path[0]
    if len(path) == 1 and path[0] in normal_fields:
        if key in ["project", "user"]:
            key = f"{key}_name"

        if type(value) == str:
            value = value.replace("'", "''")
            value = f"'{value}'"
        assert type(value) in [str, int, float], f"Invalid value type: {type(value)}"

    elif len(path) > 1 and key in json_fields:
        for k in path[1:]:
            key += f"->'{k}'"

        if type(value) in [str, int, float]:
            if type(value) == str:
                value = value.replace("'", "''")
            value = f"'{json.dumps(value)}'"

    else:
        raise ValueError(f"Invalid path: {path}")

    key = f"{table_prefix}.{key}"

    if type(value) == list:
        raise ValueError("List values are not supported yet")
        r = []
        for v in value:
            if type(v) == str:
                v = v.replace("'", "''")
                r.append(f"'{v}'")
            else:
                r.append(str(v))
        value = f"({', '.join(r)})"

        if operator == "in":
            return f"{key} IN {value}"
        elif operator == "notin":
            return f"{key} NOT IN {value}"
        else:
            raise ValueError(f"Invalid operator: {operator}")

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
    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_filter(f: Filter | None, **kwargs) -> str | None:
    """Return a SQL WHERE clause from a Filter object."""

    if f is None:
        return None

    if not f.conditions:
        return None

    result = []
    for c in f.conditions:
        if type(c) == Filter:
            if r := build_filter(c, **kwargs):
                result.append(r)
        elif type(c) == Condition:
            if r := build_condition(c, **kwargs):
                result.append(r)
        else:
            raise ValueError(f"Invalid condition: {c}")

    if not result:
        return None

    return f"({f' {f.operator.upper()} '.join(result)})"
