from enum import Enum
import json
import strawberry

from ayon_server.graphql.resolvers.common import ColumnMetadata
from ayon_server.graphql.types import ColumnStats
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger


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
    DISTRIBUTION = "distribution"


@strawberry.input(name="MetricTargetInput")
class MetricTargetInput:
    field: str = strawberry.field(
        description="The attribute path, e.g., 'attrib.fps'"
    )
    aggregations: list[StatsAggregation] = strawberry.field(
        description="List of statistical calculations to run"
    )


# Suffix to nested output key map
SUFFIX_MAP = {
    "_not_filled": "not_filled",
    "_filled": "filled",
    "_true": "checked",
    "_false": "not_checked",
    "_min": "min",
    "_max": "max",
    "_avg": "avg",
    "_sum": "sum",
    "_distribution": "distribution",
}


def generate_stats_columns(metadata_list: list[ColumnMetadata]) -> str:
    """Generates SQL-based calculations for a list of ColumnMetadata."""
    stats_fields = []

    for item in metadata_list:
        if item.is_nested:
            extracted_val = (
                f"({item.parent_json_column}->>'{item.json_key}')"
            )
            stats_fields.extend(
                _get_stats_for_column(
                    extracted_val, item.column_name, item.nested_sub_type
                )
            )
        else:
            stats_fields.extend(
                _get_stats_for_column(
                    item.column_name, item.column_name, item.data_type
                )
            )

    return ",\n    ".join(stats_fields)


def _get_stats_for_column(
    column_expr: str, column_name: str, data_type: str
) -> list[str]:
    """Returns SQL fragments for statistics based on column data type."""
    if data_type in ("numeric", "int", "float"):
        return [
            f"MIN({column_expr}::numeric) AS {column_name}_min",
            f"MAX({column_expr}::numeric) AS {column_name}_max",
            f"AVG({column_expr}::numeric) AS {column_name}_avg",
        ]
    if data_type == "string":
        return [
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} IS NOT "
            f"NULL AND {column_expr} != '') AS {column_name}_filled",
            f"COUNT(*) FILTER (WHERE {column_expr} IS NULL OR "
            f"{column_expr} = '') AS {column_name}_not_filled",
        ]
    if data_type == "uuid":
        return [
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} IS NOT "
            f"NULL) AS {column_name}_filled",
            f"COUNT(*) FILTER (WHERE {column_expr} IS NULL) "
            f"AS {column_name}_not_filled",
        ]
    if data_type == "bool":
        return [
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} = TRUE) "
            f"AS {column_name}_true",
            f"COUNT({column_expr}) FILTER (WHERE {column_expr} = FALSE OR "
            f"{column_expr} IS NULL) AS {column_name}_false",
        ]
    return []


def generate_specific_stats_columns(calculate_specific_statistics) -> str:
    """Generate aggregations strictly requested by FE definitions."""
    stats_fields = []

    for definition in calculate_specific_statistics:
        raw_field = definition.field
        column_name = raw_field.replace(".", "_")

        # Handle JSON nested extraction syntax safely
        if "." in raw_field:
            column_expr = f"({raw_field.replace('.', '->>>\'', 1)}')"
        else:
            column_expr = raw_field

        AGGR_TEMPLATES = {
            "min": f"MIN({column_expr}::numeric) AS {column_name}_min",
            "max": f"MAX({column_expr}::numeric) AS {column_name}_max",
            "avg": f"AVG({column_expr}::numeric) AS {column_name}_avg",
            "sum": f"SUM({column_expr}::numeric) AS {column_name}_sum",
            "not_filled": (
                f"COUNT(*) FILTER (WHERE {column_expr} IS NULL OR "
                f"{column_expr} = '') AS {column_name}_not_filled"
            ),
            "filled": (
                f"COUNT({column_expr}) FILTER (WHERE {column_expr} IS NOT "
                f"NULL AND {column_expr} != '') AS {column_name}_filled"
            ),
            "not_checked": (
                f"COUNT({column_expr}) FILTER (WHERE {column_expr} = FALSE "
                f"OR {column_expr} IS NULL) AS {column_name}_false"
            ),
            "checked": (
                f"COUNT({column_expr}) FILTER (WHERE {column_expr} = TRUE) "
                f"AS {column_name}_true"
            ),
            "distribution": (
                f"(SELECT json_agg(json_build_object('value', "
                f"{column_name}, 'count', cnt)) FROM (SELECT "
                f"{column_expr} as {column_name}, COUNT(*) as cnt "
                f"FROM raw_data WHERE {column_expr} IS NOT NULL "
                f"GROUP BY {column_expr}) dist) AS "
                f"{column_name}_distribution"
            ),
        }

        for op in definition.aggregations:
            op_str = op.value
            # Match template variations (e.g. 'percentage_filled' maps
            # back to 'filled')
            matched_key = next(
                (k for k in AGGR_TEMPLATES if k in op_str), None
            )
            if matched_key:
                stats_fields.append(AGGR_TEMPLATES[matched_key])

    return ",\n    ".join(stats_fields)


async def generate_field_stats(query: str) -> list[ColumnStats]:
    """Calculates field stats from prepared query."""
    grouped_data = {}
    try:
        db_result = await Postgres.fetchrow(query)
    except Exception:
        logger.warning(f"Failed to fetch {query}")
        raise

    if not db_result:
        return []

    for raw_key, value in dict(db_result).items():
        for suffix, target_key in SUFFIX_MAP.items():
            if raw_key.endswith(suffix):
                col_name = raw_key.removesuffix(suffix)
                grouped_data.setdefault(col_name, {})[target_key] = value
                break

    stats_list = []
    for col_name, metrics in grouped_data.items():
        filled = metrics.get("filled")
        not_filled = metrics.get("not_filled")
        checked = metrics.get("checked")
        not_checked = metrics.get("not_checked")

        def _calc_pct(part, total_alt):
            if part is None or total_alt is None:
                return None
            total = part + total_alt
            return (part / total) * 100.0 if total > 0 else 0.0

        percentage = _calc_pct(filled, not_filled)
        checked_percentage = _calc_pct(checked, not_checked)

        dist_obj = metrics.get("distribution")
        if isinstance(dist_obj, str):
            dist_obj = json.loads(dist_obj)

        stats_list.append(
            ColumnStats(
                column_name=col_name,
                value_filled_count=filled,
                percentage_filled=(
                    round(percentage, 2) if percentage is not None else None
                ),
                value_not_filled_count=not_filled,
                percentage_not_filled=(
                    round(100.0 - percentage, 2)
                    if percentage is not None
                    else None
                ),
                checked_count=checked,
                checked_percentage=(
                    round(checked_percentage, 2)
                    if checked_percentage is not None
                    else None
                ),
                not_checked_count=not_checked,
                not_checked_percentage=(
                    round(100.0 - checked_percentage, 2)
                    if checked_percentage is not None
                    else None
                ),
                min=metrics.get("min"),
                max=metrics.get("max"),
                avg=(
                    round(metrics["avg"], 2)
                    if metrics.get("avg") is not None
                    else None
                ),
                sum=metrics.get("sum"),
                distribution=dist_obj,
            )
        )

    return stats_list
