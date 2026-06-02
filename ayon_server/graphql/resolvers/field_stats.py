from enum import Enum
import strawberry

from ayon_server.graphql.resolvers.common import ColumnMetadata
from ayon_server.graphql.types import ColumnStats
from ayon_server.lib.postgres import Postgres


@strawberry.enum(name="StatsOperation")
class StatsAggregation(Enum):
    MIN = "min"
    MAX = "max"
    AVG = "avg"
    SUM = "sum"
    FILLED = "filled"
    NOT_FILLED = "not_filled"
    PERCENTAGE_FILLED = "percentage_filled"
    PERCENTAGE_EMPTY = "percentage_not_filled"
    CHECKED = "checked"
    NOT_CHECKED = "not_checked"
    PERCENTAGE_CHECKED = "percentage_checked"
    PERCENTAGE_NOT_CHECKED = "percentage_not_checked"

@strawberry.input(name="MetricTargetInput")
class MetricTargetInput:
    field: str = strawberry.field(
        description="The attribute path, e.g., 'attrib.fps'"
    )
    aggregations: list[StatsAggregation] = strawberry.field(
        description="List of statistical calculations to run"
    )


def generate_stats_columns(metadata_list: list[ColumnMetadata]) -> str:
    """Generates sql based calculation for list of ColumnMetadata"""
    stats_fields = []

    for item in metadata_list:
        # Handle Nested JSONB logic first
        if item.is_nested:
            extracted_val = f"({item.parent_json_column}->>'{item.json_key}')"
            stats_fields.extend(
                _get_stats_for_column(
                    extracted_val, item.column_name, item.nested_sub_type
                )
            )
            continue  # Move to the next column

        stats_fields.extend(
            _get_stats_for_column(
                item.column_name, item.column_name, item.data_type
            )
        )

    return ",\n    ".join(stats_fields)


def _get_stats_for_column(column_expr: str, column_name: str, data_type: str) -> list[str]:
    """Returns SQL fragments for statistics based on column data type."""
    if data_type in ("numeric", "int", "float"):
        return [
            f"MIN({column_expr}::numeric) AS {column_name}_min",
            f"MAX({column_expr}::numeric) AS {column_name}_max",
            f"AVG({column_expr}::numeric) AS {column_name}_avg"
        ]
    elif data_type == "string":
        return [
            f"COUNT({column_expr}) FILTER ("
            f"WHERE {column_expr} IS NOT NULL AND "
            f"{column_expr} != '') "
            f"AS {column_name}_filled",
            f"COUNT(*) FILTER ("
            f"WHERE {column_expr} IS NULL OR {column_expr} = '') "
            f"AS {column_name}_not_filled"
        ]
    elif data_type == "uuid":
        return [
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} IS NOT NULL) "
            f"AS {column_name}_filled",
            f"COUNT(*) FILTER (WHERE {column_expr} IS NULL) "
            f"AS {column_name}_not_filled"
        ]
    elif data_type == "bool":
        return [
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} = TRUE) "
            f"AS {column_name}_true",
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} = FALSE OR "
            f"{column_expr} IS NULL) "
            f"AS {column_name}_false"
        ]
    return []


def generate_specific_stats_columns(calculate_specific_statistics):
    """Generate aggregations only for FE provided definitions"""
    stats_fields = []
    for definition in calculate_specific_statistics:
        column_expr = definition.field
        column_name = column_expr.replace(".", "_")
        if "." in column_expr:
            main, key = column_expr.split(".")
            column_expr = f"({main}->>'{key}')"
        for op in definition.aggregations:
            op = op.value
            if op in ["min", "max", "avg"]:
                value = f"{op.upper()}({column_expr}::numeric) AS {column_name}_{op}"
            elif "not_filled" in op:  # for both count and percentage
                value = (
                    f"COUNT(*) FILTER ("
                    f"WHERE {column_expr} IS NULL OR {column_expr} = '') "
                    f"AS {column_name}_not_filled"
                )
            elif "filled" in op:
                value = (
                    f"COUNT({column_expr}) FILTER ("
                    f"WHERE {column_expr} IS NOT NULL AND "
                    f"{column_expr} != '') "
                    f"AS {column_name}_filled"
                )
            elif "not_checked" in op:
                value = (
                    f"COUNT({column_expr}) FILTER (WHERE {column_expr} = FALSE OR "
                    f"{column_expr} IS NULL) "
                    f"AS {column_name}_false"
                )
            elif "checked" in op:
                value = (
                    f"COUNT({column_expr}) FILTER ("
                    f"WHERE {column_expr} = TRUE) "
                    f"AS {column_name}_true"
                )
            stats_fields.append(value)

    return ",\n    ".join(stats_fields)


async def generate_field_stats(query: str) -> list[ColumnStats]:
    """Calculates field stats from prepared query"""
    # Temporary storage to group metrics by column name
    # e.g., {"folder_name": {"filled": 2, "not_filled": 0}}
    grouped_data = {}

    db_result = await Postgres.fetchrow(query)
    db_result_dict = dict(db_result)

    for raw_key, value in db_result_dict.items():
        # Identify how the key ends
        if raw_key.endswith("_not_filled"):
            col_name = raw_key.removesuffix("_not_filled")
            grouped_data.setdefault(col_name, {})["not_filled"] = value
        elif raw_key.endswith("_filled"):
            col_name = raw_key.removesuffix("_filled")
            grouped_data.setdefault(col_name, {})["filled"] = value
        elif raw_key.endswith("_true"):
            col_name = raw_key.removesuffix("_true")
            grouped_data.setdefault(col_name, {})["checked"] = value  # True counts as 'filled'
        elif raw_key.endswith("_false"):
            col_name = raw_key.removesuffix("_false")
            grouped_data.setdefault(col_name, {})["not_checked"] = value  # False counts as 'empty/false'
        elif raw_key.endswith("_min"):
            col_name = raw_key.removesuffix("_min")
            grouped_data.setdefault(col_name, {})["min"] = value
        elif raw_key.endswith("_max"):
            col_name = raw_key.removesuffix("_max")
            grouped_data.setdefault(col_name, {})["max"] = value
        elif raw_key.endswith("_avg"):
            col_name = raw_key.removesuffix("_avg")
            grouped_data.setdefault(col_name, {})["avg"] = value

    # Build the final list of Strawberry objects
    stats_list = []
    for col_name, metrics in grouped_data.items():
        filled = metrics.get("filled")
        not_filled = metrics.get("not_filled")
        checked = metrics.get("checked")
        not_checked = metrics.get("not_checked")

        percentage = None
        if filled is not None and not_filled is not None:
            total = filled + not_filled
            percentage = (filled / total) * 100.0 if total > 0 else 0.0

        checked_percentage = None
        if checked is not None and not_checked is not None:
            total = checked + not_checked
            checked_percentage = (checked / total) * 100.0 if total > 0 else 0.0

        stats_list.append(
            ColumnStats(
                column_name=col_name,
                value_filled_count=filled,
                percentage_filled=round(percentage, 2)
                    if percentage is not None else None,
                value_not_filled_count=not_filled,
                percentage_not_filled=round(100.0 - percentage, 2)
                    if percentage is not None else None,
                checked_count=checked,
                checked_percentage=round(checked_percentage, 2)
                    if checked_percentage is not None else None,
                not_checked_count=not_checked,
                not_checked_percentage=round(100.0 - checked_percentage, 2)
                    if checked_percentage is not None else None,
                min=metrics.get("min"),
                max=metrics.get("max"),
                avg=round(metrics["avg"], 2)
                    if metrics.get("avg") is not None else None,
            )
        )

    return stats_list
