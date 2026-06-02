from ayon_server.graphql.resolvers.common import ColumnMetadata
from ayon_server.graphql.types import ColumnStats
from ayon_server.lib.postgres import Postgres


def generate_stats_columns(metadata_list: list[ColumnMetadata]) -> str:
    """Generates sql based calculation for list of ColumnMetadata"""
    stats_fields = []

    for item in metadata_list:
        # Handle Nested JSONB logic first
        if item.is_nested:
            extracted_val = f"({item.parent_json_column}->>'{item.json_key}')"

            if item.nested_sub_type == "numeric":
                stats_fields.append(
                    f"MIN({extracted_val}::numeric) AS {item.column_name}_min")
                stats_fields.append(
                    f"MAX({extracted_val}::numeric) AS {item.column_name}_max")
                stats_fields.append(
                    f"AVG({extracted_val}::numeric) AS {item.column_name}_avg")
            elif item.nested_sub_type == "string":
                stats_fields.append(
                    f"COUNT({extracted_val}) FILTER ("
                    f"WHERE {extracted_val} IS NOT NULL AND "
                    f"{extracted_val} != '') "
                    f"AS {item.column_name}_filled")
                stats_fields.append(
                    f"COUNT(*) FILTER ("
                    f"WHERE {extracted_val} IS NULL OR {extracted_val} = '') "
                    f"AS {item.column_name}_not_filled")
            continue  # Move to the next column

        if item.data_type in ("numeric", "int", "float"):
            stats_fields.append(
                f"MIN({item.column_name}) AS {item.column_name}_min")
            stats_fields.append(
                f"MAX({item.column_name}) AS {item.column_name}_max")
            stats_fields.append(
                f"AVG({item.column_name}) AS {item.column_name}_avg")

        elif item.data_type == "string":
            stats_fields.append(
                f"COUNT({item.column_name}) FILTER ("
                f"WHERE {item.column_name} IS NOT NULL AND "
                f"{item.column_name} != '') "
                f"AS {item.column_name}_filled")
            stats_fields.append(
                f"COUNT(*) FILTER ("
                f"WHERE {item.column_name} IS NULL OR "
                f"{item.column_name} = '') "
                f"AS {item.column_name}_not_filled")

        elif item.data_type == "uuid":
            stats_fields.append(
                f"COUNT({item.column_name}) FILTER ("
                f"WHERE {item.column_name} IS NOT NULL)"
                f" AS {item.column_name}_filled")
            stats_fields.append(f"COUNT(*) FILTER ("
                f"WHERE {item.column_name} IS NULL) "
                f"AS {item.column_name}_not_filled")

        elif item.data_type == "bool":
            stats_fields.append(
                f"COUNT({item.column_name}) FILTER ("
                f"WHERE {item.column_name} = TRUE) "
                f"AS {item.column_name}_true")
            stats_fields.append(
                f"COUNT({item.column_name}) FILTER ("
                f"WHERE {item.column_name} = FALSE OR "
                f"{item.column_name} IS NULL) "
                f"AS {item.column_name}_false")

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
