"""Multiple sort keys in `sortBy` and compatibility with `String` variables.

The modules are loaded from their files: importing the `ayon_server.graphql`
package builds the whole schema, which requires a database connection.
"""

import asyncio
import importlib.util
import os
import sys
from types import ModuleType

import pytest
import strawberry
from graphql import parse, print_ast

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from ayon_server.exceptions import BadRequestException  # noqa: E402


def load(*path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        path[-1].removesuffix(".py"),
        os.path.join(BACKEND_DIR, "ayon_server", "graphql", *path),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy_sort_by = load("legacy_sort_by.py")
pagination = load("resolvers", "pagination.py")


def rewrite(query: str) -> tuple[str, int]:
    document, count = legacy_sort_by.rewrite_legacy_sort_by_variables(parse(query))
    return print_ast(document), count


@pytest.mark.parametrize(
    "query,expected,count",
    [
        (
            "query Q($s: String) { tasks(sortBy: $s) }",
            "$s: [String!])",
            1,
        ),
        (
            "query Q($s: String!) { tasks(sortBy: $s) }",
            "$s: [String!]!)",
            1,
        ),
        (
            'query Q($s: String = "name") { tasks(sortBy: $s) }',
            '$s: [String!] = "name")',
            1,
        ),
        (
            "query Q($s: String) { ...F } fragment F on Query { tasks(sortBy: $s) }",
            "$s: [String!])",
            1,
        ),
        # Already a list
        (
            "query Q($s: [String!]) { tasks(sortBy: $s) }",
            "$s: [String!])",
            0,
        ),
        # Not used as sortBy
        (
            "query Q($s: String) { tasks(search: $s) }",
            "$s: String)",
            0,
        ),
        # Also used by another String argument: rewriting would break that one
        (
            "query Q($s: String) { tasks(sortBy: $s, search: $s) }",
            "$s: String)",
            0,
        ),
    ],
)
def test_rewrite_legacy_sort_by_variables(query: str, expected: str, count: int):
    rewritten, rewritten_count = rewrite(query)
    assert rewritten_count == count
    assert expected in rewritten


@strawberry.type
class Query:
    @strawberry.field
    def tasks(self, sort_by: list[str] | None = None, search: str | None = None) -> str:
        return ",".join(sort_by or [])


schema = strawberry.Schema(
    query=Query,
    extensions=[legacy_sort_by.LegacySortByVariables],
)


@pytest.mark.parametrize(
    "query,variables,expected",
    [
        ('{ tasks(sortBy: "name") }', None, "name"),
        ('{ tasks(sortBy: ["status", "name"]) }', None, "status,name"),
        ("query Q($s: String) { tasks(sortBy: $s) }", {"s": "name"}, "name"),
        ("query Q($s: String) { tasks(sortBy: $s) }", {}, ""),
        ("query Q($s: String!) { tasks(sortBy: $s) }", {"s": "name"}, "name"),
        (
            "query Q($s: [String!]) { tasks(sortBy: $s) }",
            {"s": ["status", "name"]},
            "status,name",
        ),
    ],
)
def test_execution(query: str, variables: dict | None, expected: str):
    result = asyncio.run(schema.execute(query, variable_values=variables))
    assert not result.errors, result.errors
    assert result.data == {"tasks": expected}


def test_get_sort_keys():
    get_sort_keys = pagination.get_sort_keys
    assert get_sort_keys(None) == []
    assert get_sort_keys([]) == []
    assert get_sort_keys("name") == ["name"]
    assert get_sort_keys(["status", "name", "status"]) == ["status", "name"]


def test_get_sort_keys_limit():
    with pytest.raises(BadRequestException):
        pagination.get_sort_keys(["a", "b", "c", "d", "e", "f"])
    # Duplicates don't count towards the limit
    assert len(pagination.get_sort_keys(["a", "b", "c", "d", "e", "a"])) == 5


def test_with_tiebreakers():
    with_tiebreakers = pagination.with_tiebreakers
    assert with_tiebreakers(["a"], "path", "name") == ["a", "path", "name"]
    assert with_tiebreakers(["path", "name"], "path", "name") == ["path", "name"]
    assert with_tiebreakers(["name", "a"], "path", "name") == ["name", "a", "path"]
