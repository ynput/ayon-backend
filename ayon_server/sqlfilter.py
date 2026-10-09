import json
import re
from typing import Annotated, Any, Literal, Union, cast

from pydantic import (
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    root_validator,
    validator,
)

from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils.entity_id import EntityID
from ayon_server.utils.sqltool import SQLTool

ValueType = (
    StrictStr
    | StrictInt
    | StrictFloat
    | StrictBool
    | list[StrictStr]
    | list[StrictInt]
    | list[StrictFloat]
    | None
)


OperatorType = Literal[
    "eq",
    "like",
    "re",
    "lt",
    "gt",
    "lte",
    "gte",
    "ne",
    "isnull",
    "notnull",
    "in",
    "notin",
    "includes",
    "excludes",
    "includesall",
    "excludesall",
    "includesany",
    "excludesany",
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

    @validator("operator", pre=True)
    def convert_operator_to_lowercase(cls, v):
        return v.lower().replace("-", "").replace("_", "")

    @root_validator(pre=True)
    def validate_value(cls, values: dict[str, Any]):
        operator = (
            values.get("operator", "eq").lower().replace("-", "").replace("_", "")
        )
        value = values.get("value")

        if operator in ("in", "notin", "any"):
            if not isinstance(value, list):
                raise ValueError("Value must be a list")

        if operator not in ("isnull", "notnull"):
            if value is None:
                raise ValueError("Value cannot be null")

        return values


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


def filter_columns(f: QueryFilter) -> set[str]:
    """Return the set of columns a filter references.

    Columns are returned in their snake_case form, without the path to
    the key within JSON columns, so `attrib/fps` is reported as `attrib`.
    Resolvers use this to find out which joins a filter needs.
    """
    result: set[str] = set()
    for condition in f.conditions:
        if isinstance(condition, QueryFilter):
            result |= filter_columns(condition)
        else:
            key = condition.key.replace("/", ".").split(".")[0]
            result.add(camel_to_snake(key.strip()))
    return result


JSON_FIELDS = [
    "summary",
    "payload",
    "attrib",
    "data",
    "config",
    "activity_data",
    "reference_data",
]


PATH_ELEMENT_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def create_path_from_key(
    key: str,
    column_whitelist: list[str] | None = None,
    single_json_column: str | None = None,
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

    if single_json_column:
        return [single_json_column] + path

    # First element (column) must be snake_case
    column = camel_to_snake(path[0])
    if column_whitelist is not None and column not in column_whitelist:
        raise ValueError(f"Invalid key: {column}")
    path[0] = column
    return path


#
# Link conditions
#

LINK_KEY_REGEX = re.compile(r"^links(?:[/.](in|out|any)(?:[/.](.+))?)?$")

LINK_OPERATORS = (
    "includesany",
    "includesall",
    "excludesany",
    "excludesall",
    "includes",
    "excludes",
    "notnull",
    "isnull",
)


def is_link_key(key: str) -> bool:
    return key == "links" or key.startswith(("links/", "links."))


def build_link_condition(
    c: QueryCondition,
    *,
    project_name: str,
    id_column: str,
) -> str:
    """Return a SQL condition matching entities by their links.

    The key selects the links: `links[/<direction>[/<link_type>]]`,
    where direction is `in` (the entity is the link output), `out`
    (it is the input) or `any` (default), e.g. `links/in/reference|folder|folder`.

    The operator and value select the entities on the other end:

      - `notnull` / `isnull`: has / has no such link to any entity
      - `includesany` / `includes`: has such a link to any of the given IDs
      - `includesall`: has such a link to each of the given IDs
      - `excludesany` / `excludes`: has no such link to any of the given IDs
      - `excludesall`: is missing such a link to at least one of the given IDs
    """

    if not (m := LINK_KEY_REGEX.match(c.key)):
        raise ValueError(f"Invalid link key: {c.key}")
    direction = m.group(1) or "any"
    link_type = m.group(2)

    operator = c.operator
    if operator not in LINK_OPERATORS:
        raise ValueError(f"Unsupported operator for links: {operator}")

    # (column holding the entity, column holding the other end)
    ends = {
        "in": [("output_id", "input_id")],
        "out": [("input_id", "output_id")],
        "any": [("output_id", "input_id"), ("input_id", "output_id")],
    }[direction]

    base_conds = []
    if link_type:
        safe_link_type = link_type.replace("'", "''")
        base_conds.append(f"lnk.link_type = '{safe_link_type}'")

    def has_link(other_ids: list[str] | None, negate: bool = False) -> str:
        """Whether a matching link (to any of other_ids, if given) exists.

        The shapes are chosen so postgres can plan them as joins using
        the link indexes rather than as a subplan per row: `id IN (...)`
        becomes a semi-join (an OR of two EXISTS would not), and
        NOT(a OR b) is spelled out as (NOT EXISTS a AND NOT EXISTS b),
        each of which becomes an anti-join.
        """
        if not negate:
            selects = []
            for column, other in ends:
                conds = list(base_conds)
                if other_ids is not None:
                    conds.append(f"lnk.{other} IN {SQLTool.id_array(other_ids)}")
                selects.append(
                    f"SELECT lnk.{column} FROM project_{project_name}.links AS lnk"
                    f" {SQLTool.conditions(conds)}"
                )
            return f"{id_column} IN ({' UNION ALL '.join(selects)})"

        result = []
        for column, other in ends:
            conds = [f"lnk.{column} = {id_column}", *base_conds]
            if other_ids is not None:
                conds.append(f"lnk.{other} IN {SQLTool.id_array(other_ids)}")
            result.append(
                f"NOT EXISTS (SELECT 1 FROM project_{project_name}.links AS lnk"
                f" WHERE {' AND '.join(conds)})"
            )
        return result[0] if len(result) == 1 else f"({' AND '.join(result)})"

    if operator in ("notnull", "isnull"):
        return has_link(None, negate=operator == "isnull")

    value = [c.value] if isinstance(c.value, str) else c.value
    if not isinstance(value, list):
        raise ValueError("Link condition value must be a list of entity IDs")
    str_values = [v for v in value if isinstance(v, str)]
    if len(str_values) != len(value):
        raise ValueError("Link condition value must be a list of entity IDs")
    # Normalize and deduplicate (also validates the IDs)
    ids = list(dict.fromkeys(cast(str, EntityID.parse(v)) for v in str_values))
    if not ids:
        raise ValueError("Link condition requires at least one entity ID")

    if operator in ("includesany", "includes"):
        return has_link(ids)
    if operator in ("excludesany", "excludes"):
        return has_link(ids, negate=True)

    # includesall / excludesall: entities linked to each of the ids,
    # as a single (small, index driven) set rather than a condition per id
    sql_ids = SQLTool.id_array(ids)
    pairs = " UNION ALL ".join(
        f"SELECT lnk.{column} AS entity_id, lnk.{other} AS other_id"
        f" FROM project_{project_name}.links AS lnk"
        f" {SQLTool.conditions([*base_conds, f'lnk.{other} IN {sql_ids}'])}"
        for column, other in ends
    )
    linked_to_all = (
        f"{id_column} IN (SELECT entity_id FROM ({pairs}) AS pairs"
        f" GROUP BY entity_id HAVING COUNT(DISTINCT other_id) = {len(ids)})"
    )
    if operator == "includesall":
        return linked_to_all
    return f"NOT ({linked_to_all})"


def build_condition(c: QueryCondition, **kwargs) -> str:
    """Return a SQL WHERE clause from a Condition object."""

    # The project the filtered table belongs to. Conditions on columns
    # don't need it (the caller's query already names the table), but
    # the ones that query another table of the project do, e.g. links.
    project_name = kwargs.get("project_name")
    if project_name and is_link_key(c.key):
        table_prefix = kwargs.get("table_prefix")
        if not table_prefix:
            raise ValueError("Link conditions require table_prefix")
        return build_link_condition(
            c,
            project_name=project_name,
            id_column=f"{table_prefix}.id",
        )

    json_fields = kwargs.get("json_fields", JSON_FIELDS)
    single_json_column = kwargs.get("single_json_column", None)
    table_prefix = kwargs.get("table_prefix")
    column_whitelist = kwargs.get("column_whitelist", None)
    column_map: dict[str, str] = kwargs.get("column_map", {})

    path = create_path_from_key(
        c.key,
        column_whitelist,
        single_json_column=single_json_column,
    )
    value = c.value
    operator = c.operator
    cast_type = "text"
    safe_value: ValueType = None
    json_list_column: str | None = None

    column = path[0]
    if column in column_map:
        column = column_map[column]

    if len(path) == 1 and path[0] not in json_fields:
        # Hack to map project and user to their respective db column names
        # when querying from the events table
        if column in ["project", "user"]:
            column = f"{column}_name"

        if isinstance(value, str):
            if path[0] == "id" or path[0].endswith("_id"):
                safe_value = EntityID.parse(value)
            else:
                safe_value = value.replace("'", "''")
            safe_value = f"'{safe_value}'"

        elif isinstance(value, int | float):
            cast_type = "integer" if isinstance(value, int) else "number"
            safe_value = value

    elif (len(path) > 1 and path[0] in json_fields) or single_json_column:
        if single_json_column:
            column = single_json_column

        for k in path[1:]:
            column += f"->'{k}'"

        if operator in (
            "includesall",
            "excludesall",
            "includesany",
            "excludesany",
            "includes",
            "excludes",
        ):
            # JSON Field is an array, so we need to cast it to the correct type
            if isinstance(value, str):
                json_list_column = "text"
            elif isinstance(value, int | float):
                json_list_column = "integer" if isinstance(value, int) else "number"
            elif isinstance(value, list):
                if len(value) == 0:
                    raise ValueError("Empty array")
                if all(isinstance(v, str) for v in value):
                    json_list_column = "text"
                elif all(isinstance(v, (int)) for v in value):
                    json_list_column = "integer"
                elif all(isinstance(v, (float)) for v in value):
                    json_list_column = "number"
                else:
                    raise ValueError("Invalid value type in list")

        if operator in ("like", "re"):
            # JSON Field is a string, so we need to cast it to text
            if isinstance(value, str):
                safe_value = value.replace("'", "''")
                safe_value = f"'{safe_value}'"
            else:
                raise ValueError("Value must be a string for 'like' or 're' operators")

        else:
            safe_value = json.dumps(value).replace("'", "''")
            safe_value = f"'{safe_value}'::jsonb"

    else:
        raise ValueError(f"Invalid path: {path}")

    if table_prefix and path[0] not in column_map:
        column = f"{table_prefix}.{column}"

    # Provided value is a list
    if isinstance(value, list):
        # Field is a JSON array

        if json_list_column:
            if operator == "includesall":
                return f"({column})::jsonb @> {safe_value}"

            elif operator == "excludesall":
                return f"NOT ({column})::jsonb @> {safe_value}"

            elif operator == "includesany":
                return f"""EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements({column}) a(val1)
                  JOIN jsonb_array_elements({safe_value}) b(val2)
                  ON a.val1::{json_list_column} = b.val2::{json_list_column}
                )"""

            elif operator == "excludesany":
                return f"""NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements({column}) a(val1)
                  JOIN jsonb_array_elements({safe_value}) b(val2)
                  ON a.val1::{json_list_column} = b.val2::{json_list_column}
                )"""

            raise ValueError("JSON filter error")

        # Field is a Postgres array (or we are checking empty JSON array)

        if len(value) == 0:
            if operator == "eq":
                if len(path) > 1:
                    # Treat nulls in attribues as empty arrays
                    return f"((NOT EXISTS (SELECT 1 FROM jsonb_array_elements({column}))) OR {column} IS NULL)"  # noqa 501
                return f"array_length({column}, 1) IS NULL"

            if operator == "ne":
                if len(path) > 1:
                    return f"EXISTS (SELECT 1 FROM jsonb_array_elements({column}))"
                return f"array_length({column}, 1) IS NOT NULL"

        if path[0] == "id" or path[0].endswith("_id"):
            # IDs are always UUIDs
            # Let postgres cast them and validate
            escaped_list = [EntityID.parse(cast(str, v)) for v in value]

            arr_value = (
                "array[" + ", ".join([f"'{v}'::UUID" for v in escaped_list]) + "]"
            )
            cast_type = "uuid"

        elif all(isinstance(v, str) for v in value):
            escaped_list = [v.replace("'", "''") for v in value]  # type: ignore
            if len(path) > 1:
                # crawling a json, so we need to quote the values
                # this is needed for in and notin
                arr_value = (
                    "array[" + ", ".join([f"'\"{v}\"'" for v in escaped_list]) + "]"
                )
            else:
                arr_value = "array[" + ", ".join([f"'{v}'" for v in escaped_list]) + "]"
            cast_type = "text"

        elif all(isinstance(v, (int)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "integer"

        elif all(isinstance(v, (float)) for v in value):
            arr_value = "array[" + ", ".join([str(v) for v in value]) + "]"
            cast_type = "number"

        else:
            raise ValueError("Invalid value type in list")

        # Both field and value are arrays

        if operator == "includesall":
            # Field contains all values in the array
            return f"({column})::{cast_type}[] @> {arr_value}"

        elif operator == "excludesall":
            # Field does not contain the given array
            return f"NOT (({column})::{cast_type}[] @> {arr_value})"

        elif operator == "excludesany":
            # Field does not contain any of the values in the array
            return f"NOT(({column})::{cast_type}[] && {arr_value})"

        elif operator == "includesany":
            # There's an intersection between the field and the array
            return f"({column})::{cast_type}[] && {arr_value}"

        # Field is scalar, but array is provided in the filter

        elif operator == "in":
            # Field matches one of the values in the array
            return f"({column})::{cast_type} = ANY({arr_value})"

        elif operator == "notin":
            # Field does not match any of the values in the array
            return f"NOT ({column})::{cast_type} = ANY({arr_value})"

        else:
            raise ValueError(f"Invalid list operator: {operator}")

    #
    # Provided value is a scalar
    #

    if operator == "isnull":
        # Field is null. Value is ignored
        return f"{column} IS NULL"

    elif operator == "notnull":
        # Field is not null. Value is ignored
        return f"{column} IS NOT NULL"

    if safe_value is None:
        raise ValueError(f"Invalid value: {value}")

    if operator == "eq":
        if type(value) is bool:
            if value:
                return f"coalesce({column}, 'false'::jsonb)::boolean"
            return f"NOT coalesce({column}, 'false'::jsonb)::boolean"
        return f"{column} = {safe_value}"
    elif operator == "like":
        # replace last -> with ->> to get text value
        column = re.sub(r"->(?!.*->)", "->>", column)
        return f"({column}) ILIKE {safe_value}"
    elif operator == "re":
        # replace last -> with ->> to get text value
        column = re.sub(r"->(?!.*->)", "->>", column)
        return f"({column}) SIMILAR TO {safe_value}"
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

    # Field is a list

    elif operator == "includes":
        if json_list_column:
            return f"""EXISTS (
              SELECT 1
              FROM jsonb_array_elements({column}) AS elem
              WHERE elem = {safe_value}
            )"""
        return f"{safe_value} = ANY({column})"

    elif operator == "excludes":
        if json_list_column:
            return f"""NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements({column}) AS elem
              WHERE elem = {safe_value}
            )"""
        return f"NOT ({safe_value} = ANY({column}))"

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
            if c.value is None:
                if c.operator not in ("isnull", "notnull"):
                    raise ValueError("Value cannot be null unless using isnull/notnull")
                # isnull/notnull operators do not need a value

            elif isinstance(c.value, list) and not c.value:
                if c.operator in ("in", "any"):
                    result.append("FALSE")
                    continue
                elif c.operator == "notin":
                    result.append("TRUE")
                    continue
                elif c.operator not in ["eq", "ne"]:
                    # Empty list with other operators is invalid, just skip it
                    continue
                # eq and ne with empty list is okay tho.

            if r := build_condition(c, **kwargs):
                result.append(r)
        else:
            raise ValueError(f"Invalid condition: {c}")

    if not result:
        return None

    return f"({f' {f.operator.upper()} '.join(result)})"
