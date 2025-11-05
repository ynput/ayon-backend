from collections.abc import Callable, Generator
from enum import Enum
from typing import Annotated, Any, TypeVar

import strawberry
from strawberry.types.arguments import StrawberryArgumentAnnotation

from ayon_server.access.utils import folder_access_list
from ayon_server.exceptions import ForbiddenException
from ayon_server.graphql.types import Info, PageInfo
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
