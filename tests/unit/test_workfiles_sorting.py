"""Sort keys of the workfiles resolver and the SQL they are paginated with."""

import asyncio

import pytest

from ayon_server.exceptions import BadRequestException
from ayon_server.graphql.resolvers import workfiles
from ayon_server.graphql.resolvers.pagination import (
    OrderBy,
    SortColumn,
    create_pagination,
    encode_cursor,
)

NAME = workfiles.WORKFILE_NAME_EXPRESSION
TIEBREAKER = "workfiles.creation_order"


def order_by(sort_by: str | list[str] | None) -> OrderBy:
    return asyncio.run(workfiles.get_workfiles_order_by(sort_by))


def test_default():
    assert order_by(None) == [TIEBREAKER]


def test_no_nonexistent_name_column():
    """The workfiles table has no `name` column"""
    for expression in workfiles.SORT_OPTIONS.values():
        assert "workfiles.name" not in expression


def test_name_sorts_by_file_name_part_of_path():
    assert order_by("name") == [SortColumn(NAME), TIEBREAKER]
    assert "workfiles.path" in NAME
    # Both separators must be excluded from the file name,
    # the backslash must be escaped for the POSIX regex bracket
    assert r"[^/\\]*$" in NAME


@pytest.mark.parametrize(
    "sort_by,expression",
    [
        ("path", "workfiles.path"),
        ("status", "workfiles.status"),
        ("createdAt", "workfiles.created_at"),
        ("updatedAt", "workfiles.updated_at"),
    ],
)
def test_columns(sort_by: str, expression: str):
    assert order_by(sort_by) == [SortColumn(expression), TIEBREAKER]


def test_multiple_keys_and_directions():
    assert order_by(["-status", "name"]) == [
        SortColumn("workfiles.status", descending=True),
        SortColumn(NAME),
        TIEBREAKER,
    ]


def test_unknown_attribute():
    assert order_by("attrib.someAttribute") == [
        SortColumn("workfiles.attrib->>'someAttribute'"),
        TIEBREAKER,
    ]


def test_numeric_attribute_is_sorted_as_number():
    assert order_by("-attrib.fps") == [
        SortColumn("(workfiles.attrib->>'fps')::double precision", descending=True),
        TIEBREAKER,
    ]


@pytest.mark.parametrize(
    "sort_by",
    [
        "attrib.x'; DROP TABLE users; --",
        "attrib.foo'",
        "attrib.a b",
        "attrib.",
        "attrib.foo->>'bar'",
    ],
)
def test_attribute_injection_is_rejected(sort_by: str):
    with pytest.raises(BadRequestException):
        order_by(sort_by)


def test_unknown_sort_key():
    with pytest.raises(BadRequestException):
        order_by("nonexistent")
    with pytest.raises(BadRequestException):
        order_by(["name", "nonexistent"])


#
# Pagination
#


def test_name_cursor_is_compared_as_text():
    """A file name that looks like a timestamp is not cast to timestamptz"""
    after = encode_cursor(["2024-01-01T10.30", 5])
    _, conditions, _ = create_pagination(order_by("name"), first=10, after=after)
    assert "timestamptz" not in conditions
    assert "'2024-01-01T10.30'::text" in conditions


def test_name_cursor_escapes_quotes():
    after = encode_cursor(["it's.ma", 5])
    _, conditions, _ = create_pagination(order_by("name"), first=10, after=after)
    assert "'it''s.ma'::text" in conditions


@pytest.mark.parametrize("sort_by", ["status", "name", "path"])
def test_ordering_and_cursor_columns(sort_by: str):
    columns = order_by(sort_by)
    expression = workfiles.SORT_OPTIONS[sort_by]
    ordering, conditions, cursor = create_pagination(columns, first=2)
    assert conditions == ""
    assert ordering == (
        f"ORDER BY {expression} ASC NULLS LAST, {TIEBREAKER} ASC NULLS LAST LIMIT 4"
    )
    assert cursor == f"{expression} AS cursor_0, {TIEBREAKER} AS cursor_1"


def test_status_cursor():
    before = encode_cursor(["In progress", 3])
    _, conditions, _ = create_pagination(order_by("status"), last=2, before=before)
    assert conditions == (
        f"(workfiles.status, {TIEBREAKER}) < ('In progress'::text, 3)"
    )
