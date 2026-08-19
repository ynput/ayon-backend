from collections.abc import Callable, Generator
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal

import strawberry
from strawberry.types.arguments import StrawberryArgumentAnnotation

from ayon_server.access.utils import folder_access_list
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.types import Info, PageInfo
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.utils import SQLTool

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


ColumnMetadataDataType = Literal["string", "uuid", "bool", "numeric", "jsonb"]


@dataclass(frozen=True)
class ColumnMetadata:
    column_name: str
    data_type: ColumnMetadataDataType

    # These are only used if we are unpacking a JSONB field
    is_nested: bool = False
    parent_json_column: str | None = None
    json_key: str | None = None
    nested_sub_type: ColumnMetadataDataType | None = None


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
        ) -> Generator[str]:
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


def create_child_folder_ctes(
    project_name: str,
    folder_ids: list[str],
    include_self: bool = True,
) -> list[str]:
    """Create a CTE resolving folder_ids plus all of their descendant folder
    ids, by walking folders.parent_id (indexed via folder_parent_idx).

    This walks the live folders table instead of matching path strings
    against the hierarchy materialized view: a LIKE 'prefix/%' match against
    a per-row dynamic prefix can't use hierarchy_path_idx, so postgres falls
    back to scanning the whole view and can't estimate its selectivity,
    which on a project with thousands of folders skews the planner's cost
    estimate for the entire query (and, incidentally, the JIT decision that
    estimate feeds into) badly enough to dominate query time. A recursive
    walk over parent_id gives it real, estimable per-level index lookups.

    include_self=False resolves descendants only (e.g. for a "children of
    these parents" filter), without folder_ids themselves.

    NOTE: the caller must wrap the combined CTE list in "WITH RECURSIVE",
    not plain "WITH", for this CTE's self-reference to be valid SQL.

    Uses UNION, not UNION ALL: if folder_ids contains both a folder and one
    of its own descendants, that descendant's subtree would otherwise be
    reached by two different paths and recurse independently down each,
    duplicating ids (and downstream, duplicating joined result rows).
    """
    base_case = (
        f"SELECT id FROM project_{project_name}.folders "
        f"WHERE id IN {SQLTool.id_array(folder_ids)}"
        if include_self
        else f"SELECT id FROM project_{project_name}.folders "
        f"WHERE parent_id IN {SQLTool.id_array(folder_ids)}"
    )
    return [
        f"""
        child_folder_ids AS (
            {base_case}
            UNION
            SELECT f.id
            FROM project_{project_name}.folders AS f
            INNER JOIN child_folder_ids AS cf ON f.parent_id = cf.id
        )
        """,
    ]


def get_product_fields_block(
    product_alias: str = "products",
) -> tuple[list[str], list[str]]:
    """Return SQL columns and joins for resolving full product fields."""
    columns = [
        f"{product_alias}.id AS _product_id",
        f"{product_alias}.name AS _product_name",
        f"{product_alias}.folder_id AS _product_folder_id",
        f"{product_alias}.product_type AS _product_product_type",
        f"{product_alias}.product_base_type AS _product_product_base_type",
        f"{product_alias}.status AS _product_status",
        f"{product_alias}.tags AS _product_tags",
        f"{product_alias}.data AS _product_data",
        f"{product_alias}.active AS _product_active",
        f"{product_alias}.created_at AS _product_created_at",
        f"{product_alias}.updated_at AS _product_updated_at",
        f"{product_alias}.created_by AS _product_created_by",
        f"{product_alias}.updated_by AS _product_updated_by",
        f"{product_alias}.attrib AS _product_attrib",
    ]
    return columns, []


def get_folder_fields_block(
    project_name: str,
    folder_id_column: str,
    sql_joins: list[str],
    is_inner: bool = True,
) -> tuple[list[str], list[str]]:
    """Return SQL columns and joins for resolving full folder fields."""
    columns = [
        "folders.id AS _folder_id",
        "folders.name AS _folder_name",
        "folders.label AS _folder_label",
        "folders.folder_type AS _folder_folder_type",
        "folders.thumbnail_id AS _folder_thumbnail_id",
        "folders.parent_id AS _folder_parent_id",
        "folders.attrib AS _folder_attrib",
        "folders.data AS _folder_data",
        "folders.active AS _folder_active",
        "folders.status AS _folder_status",
        "folders.tags AS _folder_tags",
        "folders.created_at AS _folder_created_at",
        "folders.updated_at AS _folder_updated_at",
        "projects.attrib as _folder_project_attributes",
        "folder_ex.attrib as _folder_inherited_attributes",
    ]
    exported_join = "INNER" if is_inner else "LEFT"
    joins: list[str] = []

    def has_join(alias_or_table: str) -> bool:
        all_joins = sql_joins + joins
        return any(alias_or_table in j for j in all_joins)

    if not has_join(".folders"):
        joins.append(
            f"""
            INNER JOIN project_{project_name}.folders AS folders
                ON folders.id = {folder_id_column}
            """
        )

    if not has_join("folder_ex"):
        joins.append(
            f"""
            {exported_join} JOIN project_{project_name}.exported_attributes AS folder_ex
                ON folders.id = folder_ex.folder_id
            """
        )

    if not has_join("public.projects"):
        joins.append(
            f"""
            INNER JOIN public.projects AS projects
                ON projects.name ILIKE '{project_name}'
            """
        )
    return columns, joins


#
# Actual resolver
#


async def resolve[R](
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
) -> R:
    """Return a connection object from a query."""

    if first is not None:
        count = first
    elif last is not None:
        count = last
    else:
        count = first = DEFAULT_PAGE_SIZE

    edges: list[Any] = []
    # Now execute the original query for the actual data
    async for record in Postgres.iterate(query):
        # Create a standard dictionary from the record
        record_dict = dict(record)

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
                logger.trace(f"Skipping node {node_type} due to ForbiddenException")
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


def build_search_conditions(
    search: str,
    columns: list[str],
    *,
    version_check: bool = False,
) -> str | None:
    """Build SQL search conditions from a search string.

    The search string is split by commas (OR between comma-separated parts).
    Within each part, slugified terms are AND'd together.
    Within each term, the specified columns are OR'd together.

    Returns a SQL condition string, or None if search is empty
    or no conditions could be built.
    """
    parts = search.split(",")
    t1_conds = []

    for part in parts:
        terms = part.lower().replace("'", "''").split(" ")
        t2_conds = []
        for term in terms:
            term = term.replace("\\", "\\\\").replace("_", "\\_")
            if not term:
                continue
            sub_conditions = [f"{col} ILIKE '%{term}%'" for col in columns]
            if version_check:
                if term.isdigit():
                    sub_conditions.append(f"versions.version = {int(term)}")
                elif term.startswith("v") and term[1:].isdigit():
                    sub_conditions.append(f"versions.version = {int(term[1:])}")
            t2_conds.append(
                f"({SQLTool.conditions(sub_conditions, 'OR', add_where=False)})"
            )
        if t2_conds:
            t1_conds.append(f"({SQLTool.conditions(t2_conds, 'AND', add_where=False)})")

    if t1_conds:
        return f"({SQLTool.conditions(t1_conds, 'OR', add_where=False)})"

    return None
