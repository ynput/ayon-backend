from collections.abc import Callable, Generator
from enum import Enum
from typing import Annotated, Any, TypeVar

import strawberry
from strawberry.types.arguments import StrawberryArgumentAnnotation

from ayon_server.access.utils import folder_access_list
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.types import Info, PageInfo, ColumnStats
from ayon_server.lib.postgres import Postgres

from .pagination import encode_cursor

DEFAULT_PAGE_SIZE = 100


@strawberry.enum
class HasLinksFilter(Enum):
    NONE = "none"
    IN = "in"
    OUT = "out"
    ANY = "any"
    BOTH = "both"


@strawberry.input
class AttributeFilterInput:
    name: str
    values: list[str]


def argdesc(description: str) -> StrawberryArgumentAnnotation:
    description = "\n".join([line.strip() for line in description.split("\n")])
    return strawberry.argument(description=description)


def sortdesc(sort_options: dict[str, str]) -> StrawberryArgumentAnnotation:
    """Return a textual description for sorting argument"""
    description = f"Sort by one of {', '.join(sort_options.keys())}"
    return strawberry.argument(description=description)


ARGFirst = Annotated[int | None, argdesc("Pagination: first")]
ARGAfter = Annotated[str | None, argdesc("Pagination: first")]
ARGLast = Annotated[int | None, argdesc("Pagination: last")]
ARGBefore = Annotated[str | None, argdesc("Pagination: before")]
ARGIds = Annotated[list[str] | None, argdesc("List of ids to be returned")]
ARGHasLinks = Annotated[HasLinksFilter | None, argdesc("Filter by links presence")]


class FieldInfo:
    """Info object parser.

    Parses a strawberry.Info object and returns a list of selected fields.
    list of roots may be provided - roots will be stripped from the paths.

    List of roots must be ordered from the most specific to the most general,
    otherwise the stripping will not work.

    Paths are returned as a comma separated string.
    """

    def __init__(self, info: Info, roots: list[str] | None = None):
        self.info = info
        if roots is None:
            self.roots = []
        else:
            self.roots = roots

        def parse_fields(
            fields: list[Any],
            name: str | None = None,
        ) -> Generator[str, None, None]:
            for field in fields:
                if hasattr(field, "name"):
                    fname = name + "." + field.name if name else field.name
                    yield fname
                    yield from parse_fields(field.selections, fname)

                elif hasattr(field, "selections"):
                    yield from parse_fields(field.selections, None)

        self.fields: list[str] = []
        for field in parse_fields(info.selected_fields):
            for root in self.roots:
                if field.startswith(root + "."):
                    field = field.removeprefix(root + ".")
                    break
            if field in self.fields:
                continue
            self.fields.append(field)

    def __iter__(self):
        return self.fields.__iter__()

    def __contains__(self, field: str) -> bool:
        return field in self.fields

    def has_any(self, *fields: str) -> bool:
        for field in fields:
            if field in self.fields:
                return True
        return False

    def any_endswith(self, *fields: str) -> bool:
        for field in fields:
            for f in self.fields:
                if f.split(".")[-1] == field:
                    return True
        return False

    def find_field(self, name: str) -> Any | None:
        # TODO: figure out what this thing returns

        # return SelectedField object that matches the name
        # this recursively searches the selected fields

        def _find_field(field, name: str) -> str | None:
            if field.name == name:
                return field
            for selection in field.selections:
                if hasattr(selection, "name"):
                    result = _find_field(selection, name)
                    if result is not None:
                        return result
            return None

        for sfield in self.info.selected_fields:
            result = _find_field(sfield, name)
            if result is not None:
                return result

        return None


async def create_folder_access_list(root, info) -> list[str] | None:
    user = info.context["user"]
    project_name = root.project_name
    # Why this was here? It doesn't make sense.
    # if root.__class__.__name__ != "ProjectNode":
    #     return None
    return await folder_access_list(user, project_name)


#
# Actual resolver
#

R = TypeVar("R")


async def resolve(
    connection_type: Callable[..., R],
    edge_type,
    node_type,
    query: str,
    *,
    project_name: str | None = None,
    first: int | None = None,
    last: int | None = None,
    context: dict[str, Any] | None = None,
    order_by: list[str] | None = None,
    calculate_statistics: bool = False
) -> R:
    """Return a connection object from a query."""

    metadata_query = None

    if first is not None:
        count = first
    elif last is not None:
        count = last
    else:
        count = first = DEFAULT_PAGE_SIZE

    edges: list[Any] = []
    column_metadata_list = None
    # Now execute the original query for the actual data
    async for record in Postgres.iterate(query):
        # Create a standard dictionary from the record
        record_dict = dict(record)

        if not calculate_statistics:
            # Create cursor:
            # We need to do that first, because we need to get rid of
            # the cursor data from the record

            cdata = []
            for i, _ in enumerate(order_by or []):
                cdata.append(record_dict.pop(f"cursor_{i}"))
            cursor = encode_cursor(cdata)

            if node_type is not None:
                try:
                    node = await node_type.from_record(
                        project_name, record_dict, context=context
                    )
                except ForbiddenException:
                    continue
                edges.append(edge_type(node=node, cursor=cursor))

            else:
                # This is for entity list items. They need to be resolved,
                # But the actual node is created on the edge, not here
                try:
                    payload = {**record_dict, "cursor": cursor}
                    edge = await edge_type.from_record(
                        project_name, payload, context=context
                    )
                except ForbiddenException:
                    continue
                edges.append(edge)

                if count and count == len(edges):
                    break
        else:
            column_metadata_list = _parse_db_stats_to_graphql(record_dict)

    has_next_page = False
    has_previous_page = False
    start_cursor = None
    end_cursor = None

    if first:
        has_next_page = len(edges) >= first
        has_previous_page = False  # TODO
        start_cursor = edges[0].cursor if edges else None
        end_cursor = edges[-1].cursor if edges else None
    elif last:
        has_next_page = False  # TODO
        has_previous_page = len(edges) >= last
        start_cursor = edges[0].cursor if edges else None
        end_cursor = edges[-1].cursor if edges else None
        # edges.reverse()

    page_info = PageInfo(
        has_next_page=has_next_page,
        has_previous_page=has_previous_page,
        start_cursor=start_cursor,
        end_cursor=end_cursor,
        column_metadata=column_metadata_list
    )

    return connection_type(edges=edges, page_info=page_info)


def get_has_links_conds(
    project_name: str,
    id_field: str,
    filter: HasLinksFilter | None,
) -> list[str]:
    if filter is None:
        return []
    if filter == HasLinksFilter.IN:
        return [f"{id_field} IN (SELECT output_id FROM project_{project_name}.links)"]
    if filter == HasLinksFilter.OUT:
        return [f"{id_field} IN (SELECT input_id FROM project_{project_name}.links)"]
    if filter == HasLinksFilter.ANY:
        return [
            f"({id_field} IN (SELECT input_id FROM project_{project_name}.links) OR "
            f"{id_field} IN (SELECT output_id FROM project_{project_name}.links))",
        ]
    if filter == HasLinksFilter.BOTH:
        return [
            f"{id_field} IN (SELECT output_id FROM project_{project_name}.links)",
            f"{id_field} IN (SELECT input_id FROM project_{project_name}.links)",
        ]
    raise ValueError("Wrong has_links value")


def generate_stats_columns(columns_with_types):
    """
    columns_with_types: A list of dicts or tuples containing (column_alias, data_type)
    e.g., [("cursor_0", "numeric"), ("folder_name", "string"), ("path", "string")]
    """
    stats_fields = []

    for item in columns_with_types:
        col_alias, col_type = item[0], item[1]

        if col_type in ("numeric", "int", "float"):
            stats_fields.append(f"MIN({col_alias}) AS {col_alias}_min")
            stats_fields.append(f"MAX({col_alias}) AS {col_alias}_max")
            stats_fields.append(f"AVG({col_alias}) AS {col_alias}_avg")

        elif col_type in ("string", "text"):
            stats_fields.append(
                f"COUNT({col_alias}) FILTER (WHERE {col_alias} IS NOT NULL AND {col_alias} != '') AS {col_alias}_filled"
            )
            stats_fields.append(
                f"COUNT(*) FILTER (WHERE {col_alias} IS NULL OR {col_alias} = '') AS {col_alias}_not_filled"
            )

        elif col_type in ("boolean", "bool"):
            stats_fields.append(
                f"COUNT({col_alias}) FILTER (WHERE {col_alias} = TRUE) AS {col_alias}_true"
            )
            stats_fields.append(
                f"COUNT({col_alias}) FILTER (WHERE {col_alias} = FALSE OR {col_alias} IS NULL) AS {col_alias}_false"
            )
        elif col_type == "uuid":
            stats_fields.append(
                f"COUNT({col_alias}) FILTER (WHERE {col_alias} IS NOT NULL) AS {col_alias}_filled"
            )
            stats_fields.append(
                f"COUNT(*) FILTER (WHERE {col_alias} IS NULL) AS {col_alias}_not_filled"
            )
        elif col_type == "jsonb_nested":
            # Expects item to look like: ("alias_name", "jsonb_nested", "parent_json_column", "nested_key_name", "sub_type")
            parent_col, json_key, sub_type = item[2], item[3], item[4]

            # Use PostgreSQL ->> operator to extract the value as text
            extracted_val = f"({parent_col}->>'{json_key}')"

            if sub_type == "numeric":
                stats_fields.append(f"MIN({extracted_val}::numeric) AS {col_alias}_min")
                stats_fields.append(f"MAX({extracted_val}::numeric) AS {col_alias}_max")
                stats_fields.append(f"AVG({extracted_val}::numeric) AS {col_alias}_avg")
            elif sub_type == "string":
                stats_fields.append(
                    f"COUNT({extracted_val}) FILTER (WHERE {extracted_val} IS NOT NULL AND {extracted_val} != '') AS {col_alias}_filled")
                stats_fields.append(
                    f"COUNT(*) FILTER (WHERE {extracted_val} IS NULL OR {extracted_val} = '') AS {col_alias}_not_filled")

    return ",\n    ".join(stats_fields)


def _parse_db_stats_to_graphql(db_result: dict) -> list[ColumnStats]:
    # Temporary storage to group metrics by column name
    # e.g., {"folder_name": {"filled": 2, "not_filled": 0}}
    grouped_data = {}

    for raw_key, value in db_result.items():
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
                avg=round(metrics["avg"], 2) if metrics.get("avg") is not None else None,
            )
        )

    return stats_list
