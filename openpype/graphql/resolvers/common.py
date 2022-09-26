from enum import Enum
from typing import Annotated, Any, Callable, Generator, TypeVar

import strawberry
from strawberry.arguments import StrawberryArgumentAnnotation
from strawberry.types import Info

from openpype.access.utils import folder_access_list
from openpype.graphql.types import PageInfo
from openpype.lib.postgres import Postgres
from openpype.utils import EntityID, validate_name

DEFAULT_PAGE_SIZE = 100


@strawberry.enum
class HasLinksFilter(Enum):
    NONE = "none"
    IN = "in"
    OUT = "out"
    ANY = "any"
    BOTH = "both"


def argdesc(description: str) -> StrawberryArgumentAnnotation:
    description = "\n".join([line.strip() for line in description.split("\n")])
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
                if not hasattr(field, "name"):
                    continue
                fname = name + "." + field.name if name else field.name
                yield fname
                yield from parse_fields(field.selections, fname)

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


async def create_folder_access_list(root, info) -> list[str] | None:
    user = info.context["user"]
    project_name = root.project_name
    if root.__class__.__name__ != "ProjectNode":
        return None
    return await folder_access_list(user, project_name, "read")


def create_pagination(
    order_by: str,
    first: int | None = None,
    after: str | None = None,
    last: int | None = None,
    before: str | None = None,
) -> tuple[str, list[str]]:
    pagination = ""
    sql_conditions = []

    if not (last or first):
        first = 100

    if order_by.endswith("id"):
        # should raise value error in case of invalid cursor
        if after:
            after = f"'{EntityID.parse(after)}'"
        elif before:
            before = f"'{EntityID.parse(after)}'"
    elif order_by == "name":
        if after:
            if not validate_name(after):
                raise ValueError("Wrong name")
            after = f"'{after}'"
        elif before:
            if not validate_name(before):
                raise ValueError("Wrong name")
            before = f"'{before}'"

    if first:
        pagination += f"ORDER BY {order_by} ASC LIMIT {first}"
        if after:
            sql_conditions.append(f"{order_by} > {after}")
    elif last:
        pagination += f"ORDER BY {order_by} DESC LIMIT {last}"
        if before:
            sql_conditions.append(f"{order_by} < '{EntityID.parse(before)}'")
    return pagination, sql_conditions


R = TypeVar("R")


async def resolve(
    connection_type: Callable[..., R],
    edge_type,
    node_type,
    project_name: str | None,
    query: str,
    first: int | None = None,
    last: int | None = None,
    context: dict = None,
    order_by: str = "id",
) -> R:
    """Return a connection object from a query."""

    if first is not None:
        count = first
    elif last is not None:
        count = last
    else:
        count = first = DEFAULT_PAGE_SIZE

    edges: list[Any] = []
    async for record in Postgres.iterate(query):
        if count and count <= len(edges):
            break

        if project_name:
            node = node_type.from_record(project_name, record, context=context)
        else:
            node = node_type.from_record(record, context=context)
        cursor = record[order_by.split(".")[-1]]
        if order_by.endswith("id"):
            cursor = EntityID.parse(cursor)
        edges.append(edge_type(node=node, cursor=cursor))

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
