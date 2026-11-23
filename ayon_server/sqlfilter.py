import json
import re
from collections.abc import Callable
from typing import Annotated, Any, Literal, Union, cast

from pydantic import (
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils.entity_id import EntityID

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
    "notlike",
    "contains",
    "startswith",
    "endswith",
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

TEXT_OPERATORS = ("like", "notlike", "contains", "startswith", "endswith", "re")


def camel_to_snake(name):
    """Convert camelCase or PascalCase to snake_case."""
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return name


def anchored_pattern(operator: str, value: str) -> str:
    """Turn the value of startswith/endswith into an ILIKE pattern.

    % _ and \\ in the value are literals. Other operators pass through.
    """
    if operator not in ("startswith", "endswith"):
        return value
    value = re.sub(r"([\\%_])", r"\\\1", value)
    return f"{value}%" if operator == "startswith" else f"%{value}"


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
            description=(
                "Comparison operator. Text operators: like, notlike, contains, "
                "startswith, endswith, re"
            ),
            example="eq",
        ),
    ] = "eq"

    @field_validator("operator", mode="before")
    @classmethod
    def convert_operator_to_lowercase(cls, v):
        return v.lower().replace("-", "").replace("_", "")

    @model_validator(mode="before")
    @classmethod
    def validate_value(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
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

    @field_validator("operator", mode="before")
    @classmethod
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
# Trait fields and trait ids of representations
#

# Columns derived from representation traits by a database trigger
# (public.set_representation_trait_columns).
TRAIT_FIELDS_COLUMN = "trait_fields"
TRAIT_IDS_COLUMN = "trait_ids"

# Filter key of a trait field: traits/<trait id>/<field>. A versionless
# trait id matches every version of the trait that has the field.
TRAIT_FIELD_KEY_PREFIX = "traits/"
TRAIT_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)*$")
TRAIT_VERSION_SUFFIX_REGEX = re.compile(r"\.v(\d+)$")

# versionless trait id -> version -> field -> field type
TraitFieldTypes = dict[str, dict[int, dict[str, str]]]

_LIST_FIELD_TYPES = ("list_of_strings", "list_of_integers")
_FIELD_COMPARISONS = {"lt": "<", "gt": ">", "lte": "<=", "gte": ">="}
_INCLUSION_OPERATORS = (
    "includes",
    "excludes",
    "includesall",
    "excludesall",
    "includesany",
    "excludesany",
)
# Operators that also match representations without the field. Across
# trait versions their conditions are combined with AND, others with OR.
_ABSENCE_OPERATORS = ("isnull", "excludes", "excludesall", "excludesany")


def _field_value_ok(value: Any, field_type: str) -> bool:
    if field_type in ("integer", "list_of_integers"):
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type == "float":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if field_type in ("string", "list_of_strings"):
        return isinstance(value, str)
    if field_type == "boolean":
        return isinstance(value, bool)
    return False


def _jsonb_literal(data: Any) -> str:
    return "'" + json.dumps(data).replace("'", "''") + "'::jsonb"


def _build_json_field_condition(  # noqa: C901
    c: QueryCondition,
    trait_key: str,
    field: str,
    column: str,
    field_type: str | None,
) -> str:
    """Return a SQL condition on one field of one trait version.

    `column` holds `{"<versioned trait id>": {"<field>": value}}` with a
    GIN (jsonb_path_ops) index. Equality and inclusion compile to
    containment (`@>`), so they use the index. Other operators are
    evaluated per row.

    Negative operators (`ne`, `notin`, `notlike`) match only rows that
    have the field. `excludes*` match rows without the field too.
    """

    operator = c.operator
    value = c.value

    # Inclusion operators work on list fields also when the type is unknown
    is_list = field_type in _LIST_FIELD_TYPES or (
        field_type is None and operator in _INCLUSION_OPERATORS
    )
    accessor = f"{column}->'{trait_key}'->'{field}'"
    text = f"{column}->'{trait_key}'->>'{field}'"

    def contains(item: Any) -> str:
        if is_list and not isinstance(item, list):
            item = [item]
        return f"{column} @> {_jsonb_literal({trait_key: {field: item}})}"

    def any_of(items: list[Any]) -> str:
        if not items:
            return "FALSE"
        return "(" + " OR ".join(contains(item) for item in items) + ")"

    items = value if isinstance(value, list) else [value]

    if operator == "isnull":
        return f"{accessor} IS NULL"
    if operator == "notnull":
        return f"{accessor} IS NOT NULL"

    if operator in TEXT_OPERATORS:
        pattern = anchored_pattern(operator, cast(str, value))
        safe_value = "'" + pattern.replace("'", "''") + "'"
        if operator in ("like", "startswith", "endswith"):
            return f"({text}) ILIKE {safe_value}"
        if operator == "notlike":
            return f"({accessor} IS NOT NULL AND NOT ({text}) ILIKE {safe_value})"
        if operator == "contains":
            return f"strpos(lower({text}), lower({safe_value})) > 0"
        return f"({text}) SIMILAR TO {safe_value}"

    if operator in ("eq", "ne") and value == []:
        # Empty lists are not stored, so an empty list is a missing field
        return f"{accessor} IS {'' if operator == 'eq' else 'NOT '}NULL"
    if operator == "eq" and isinstance(value, list):
        # Exact list
        return f"{accessor} = {_jsonb_literal(value)}"
    if operator in ("eq", "includes", "includesall"):
        return contains(value)
    if operator in ("in", "includesany"):
        return any_of(items)
    if operator in ("excludes", "excludesall"):
        return f"NOT {contains(value)}"
    if operator == "excludesany":
        return f"NOT {any_of(items)}"
    if operator == "ne":
        return f"({accessor} IS NOT NULL AND NOT {contains(value)})"
    if operator == "notin":
        return f"({accessor} IS NOT NULL AND NOT {any_of(items)})"

    if operator in _FIELD_COMPARISONS:
        sql_operator = _FIELD_COMPARISONS[operator]
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ValueError(f"Invalid value for '{operator}': {value!r}")
        if isinstance(value, int | float):
            # Compare only numbers
            return (
                f"(jsonb_typeof({accessor}) = 'number'"
                f" AND ({text})::numeric {sql_operator} {value!r})"
            )
        return (
            f"(jsonb_typeof({accessor}) = 'string'"
            f" AND {accessor} {sql_operator} {_jsonb_literal(value)})"
        )

    raise ValueError(f"Unsupported trait field operator: {operator}")


def parse_trait_field_key(key: str) -> tuple[str, str]:
    """Split a `traits/<trait id>/<field>` key to the trait id and field."""

    rest = key[len(TRAIT_FIELD_KEY_PREFIX) :]
    if "/" not in rest:
        raise ValueError("Trait field key must be traits/<trait id>/<field>")
    trait_id, field = rest.rsplit("/", 1)
    if not TRAIT_ID_REGEX.match(trait_id):
        raise ValueError(f"Invalid trait id: {trait_id}")
    if not PATH_ELEMENT_REGEX.match(field):
        raise ValueError(f"Invalid trait field: {field}")
    return trait_id, field


def build_trait_field_condition(
    c: QueryCondition,
    column: str,
    trait_field_types: TraitFieldTypes | None,
) -> str:
    """Return a SQL condition on a trait field of a representation.

    The key is `traits/<trait id>/<field>`. A versioned trait id matches
    only that version. A versionless one matches every version of the
    trait whose definition has the field, so `trait_field_types` (from
    the trait definitions) is required. It also validates the values:
    an unknown trait or field, or a value of a wrong type, raises
    ValueError.
    """

    if trait_field_types is None:
        raise ValueError("Trait field filters are not supported here")

    trait_id, field = parse_trait_field_key(c.key)
    match = TRAIT_VERSION_SUFFIX_REGEX.search(trait_id)
    versionless_id = TRAIT_VERSION_SUFFIX_REGEX.sub("", trait_id)
    versions = trait_field_types.get(versionless_id)
    if not versions:
        raise ValueError(f"Unknown trait: {versionless_id}")
    if match:
        version = int(match[1])
        if version not in versions:
            raise ValueError(f"Unknown trait: {trait_id}")
        versions = {version: versions[version]}

    check_values = c.operator not in ("isnull", "notnull") and (
        c.operator not in TEXT_OPERATORS
    )
    items = c.value if isinstance(c.value, list) else [c.value]
    conditions: list[str] = []
    known_field = False
    for version, fields in sorted(versions.items()):
        field_type = fields.get(field)
        if field_type is None:
            continue
        known_field = True
        if check_values and not all(
            _field_value_ok(item, field_type) for item in items
        ):
            # The value does not fit this version, e.g. a string field
            # that became a number in a later version
            continue
        conditions.append(
            _build_json_field_condition(
                c, f"{versionless_id}.v{version}", field, column, field_type
            )
        )

    if not known_field:
        raise ValueError(f"Unknown trait field: {versionless_id}/{field}")
    if not conditions:
        raise ValueError(
            f"Invalid value {c.value!r} for trait field {versionless_id}/{field}"
        )
    if len(conditions) == 1:
        return conditions[0]
    joiner = " AND " if c.operator in _ABSENCE_OPERATORS else " OR "
    return "(" + joiner.join(conditions) + ")"


def build_trait_ids_condition(c: QueryCondition, column: str) -> str:
    """Return a SQL condition on trait ids of a representation.

    Trait ids hold both versioned and versionless ids. The column has
    a GIN index, used by the `includes*` operators.
    """

    value = c.value
    items = value if isinstance(value, list) else [value]
    if not items or not all(isinstance(item, str) for item in items):
        raise ValueError("Trait ids must be strings")
    escaped = ", ".join(
        "'" + cast(str, item).replace("'", "''") + "'" for item in items
    )
    array = f"ARRAY[{escaped}]::varchar[]"

    operator = c.operator
    if operator in ("includes", "includesall", "eq"):
        return f"{column} @> {array}"
    if operator in ("includesany", "in"):
        return f"{column} && {array}"
    if operator in ("excludes", "excludesall"):
        return f"NOT {column} @> {array}"
    if operator in ("excludesany", "notin", "ne"):
        return f"NOT {column} && {array}"
    raise ValueError(f"Unsupported trait ids operator: {operator}")


def build_condition(c: QueryCondition, **kwargs) -> str:
    """Return a SQL WHERE clause from a Condition object."""

    json_fields = kwargs.get("json_fields", JSON_FIELDS)
    single_json_column = kwargs.get("single_json_column", None)
    table_prefix = kwargs.get("table_prefix")
    column_whitelist = kwargs.get("column_whitelist", None)
    column_map: dict[str, str | Callable[[str | None], str]] = kwargs.get(
        "column_map", {}
    )

    if not single_json_column and c.key.startswith(TRAIT_FIELD_KEY_PREFIX):
        if column_whitelist is not None and TRAIT_FIELDS_COLUMN not in column_whitelist:
            raise ValueError(f"Invalid key: {c.key}")
        column = TRAIT_FIELDS_COLUMN
        if table_prefix:
            column = f"{table_prefix}.{column}"
        return build_trait_field_condition(c, column, kwargs.get("trait_field_types"))

    path = create_path_from_key(
        c.key,
        column_whitelist,
        single_json_column=single_json_column,
    )
    if not single_json_column and path[0] == TRAIT_IDS_COLUMN:
        if len(path) != 1:
            raise ValueError(f"Invalid path: {path}")
        column = path[0]
        if table_prefix:
            column = f"{table_prefix}.{column}"
        return build_trait_ids_condition(c, column)

    value = c.value
    operator = c.operator
    cast_type = "text"
    safe_value: ValueType = None
    json_list_column: str | None = None
    column_is_jsonb = False

    if operator in TEXT_OPERATORS and not isinstance(value, str):
        raise ValueError(f"Value must be a string for the '{operator}' operator")

    column = path[0]
    mapped_attribute = False
    if column in column_map:
        mapped = column_map[column]
        if callable(mapped):
            mapped_attribute = len(path) > 1 and path[0] in json_fields
            column = mapped(path[1] if mapped_attribute else None)
        else:
            column = mapped

    if len(path) == 1 and path[0] not in json_fields:
        # Hack to map project and user to their respective db column names
        # when querying from the events table
        if column in ["project", "user"]:
            column = f"{column}_name"

        if isinstance(value, str):
            if path[0] == "id" or path[0].endswith("_id"):
                safe_value = EntityID.parse(value)
            else:
                safe_value = anchored_pattern(operator, value).replace("'", "''")
            safe_value = f"'{safe_value}'"

        elif isinstance(value, int | float):
            cast_type = "integer" if isinstance(value, int) else "number"
            safe_value = value

    elif (len(path) > 1 and path[0] in json_fields) or single_json_column:
        column_is_jsonb = True
        if single_json_column:
            column = single_json_column

        for k in path[2:] if mapped_attribute else path[1:]:
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

        if operator in TEXT_OPERATORS:
            # JSON Field is a string, so we need to cast it to text
            pattern = anchored_pattern(operator, cast(str, value))
            safe_value = "'" + pattern.replace("'", "''") + "'"

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
                return f"NOT COALESCE(({column})::jsonb @> {safe_value}, FALSE)"

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
            return f"NOT COALESCE(({column})::{cast_type}[] @> {arr_value}, FALSE)"

        elif operator == "excludesany":
            # Field does not contain any of the values in the array
            return f"NOT COALESCE(({column})::{cast_type}[] && {arr_value}, FALSE)"

        elif operator == "includesany":
            # There's an intersection between the field and the array
            return f"({column})::{cast_type}[] && {arr_value}"

        # Field is scalar, but array is provided in the filter

        elif operator == "in":
            # Field matches one of the values in the array
            return f"({column})::{cast_type} = ANY({arr_value})"

        elif operator == "notin":
            # Field does not match any of the values in the array.
            # NULL (unset) fields match too, since they are not in the array
            return f"NOT COALESCE(({column})::{cast_type} = ANY({arr_value}), FALSE)"

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

    if operator in TEXT_OPERATORS:
        if mapped_attribute:
            # A resolved value may be a COALESCE of several JSON accesses.
            column = f"({column}) #>> '{{}}'"
        else:
            column = re.sub(r"->(?!.*->)", "->>", column)

    if operator == "eq":
        if type(value) is bool:
            if column_is_jsonb:
                boolean_expr = f"coalesce({column}, 'false'::jsonb)::boolean"
            else:
                boolean_expr = f"coalesce({column}, FALSE)"
            return boolean_expr if value else f"NOT {boolean_expr}"
        return f"{column} = {safe_value}"
    elif operator in ("like", "startswith", "endswith"):
        return f"({column}) ILIKE {safe_value}"
    elif operator == "notlike":
        # a missing value does not match the pattern, so it passes the filter
        return f"NOT coalesce(({column}) ILIKE {safe_value}, FALSE)"
    elif operator == "contains":
        # literal substring match: unlike ILIKE, % _ and \ are not special
        return f"strpos(lower({column}), lower({safe_value})) > 0"
    elif operator == "re":
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
        # NULL (unset) fields are not equal to the value either
        return f"{column} IS DISTINCT FROM {safe_value}"

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
        return f"NOT COALESCE({safe_value} = ANY({column}), FALSE)"

    else:
        raise ValueError(f"Unsupported operator: {operator}")


def build_filter(f: QueryFilter | None, **kwargs) -> str | None:
    """Return a SQL WHERE clause from a Filter object."""

    if f is None:
        return None

    if not f.conditions:
        logger.trace(f"Empty conditions {f.model_dump()}")
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
