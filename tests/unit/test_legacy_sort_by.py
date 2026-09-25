"""Backwards compatibility for `String` typed `sortBy` variables."""

import asyncio

import pytest
import strawberry
from graphql import (
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    parse,
    print_ast,
    validate,
)

from ayon_server.graphql import router as graphql_router
from ayon_server.graphql.legacy_attrib import rewrite_legacy_attrib_selections
from ayon_server.graphql.legacy_sort_by import (
    LegacySortByVariables,
    rewrite_legacy_sort_by_variables,
)
from ayon_server.graphql.resolvers.common import get_sort_keys
from ayon_server.graphql.resolvers.pagination import with_tiebreakers


def rewrite(query: str) -> tuple[str, int]:
    document, count = rewrite_legacy_sort_by_variables(parse(query))
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


def _sort_by_arguments():
    schema = graphql_router.schema._schema  # type: ignore[attr-defined]
    for type_name, gql_type in schema.type_map.items():
        if not isinstance(gql_type, GraphQLObjectType):
            continue
        for field_name, field in gql_type.fields.items():
            if arg := field.args.get("sortBy"):
                yield f"{type_name}.{field_name}", arg.type


def test_schema_sort_by_arguments_are_string_lists():
    """The rewrite assumes every `sortBy` argument is `[String!]`."""
    arguments = list(_sort_by_arguments())
    assert arguments
    for name, arg_type in arguments:
        assert isinstance(arg_type, GraphQLList), name
        assert isinstance(arg_type.of_type, GraphQLNonNull), name
        assert str(arg_type.of_type.of_type) == "String", name


LEGACY_QUERY = """
query Legacy($projectName: String!, $sortBy: String) {
  project(name: $projectName) {
    folders(sortBy: $sortBy) { edges { node { id } } }
    tasks(sortBy: $sortBy) { edges { node { id } } }
    products(sortBy: $sortBy) { edges { node { id } } }
    versions(sortBy: $sortBy) { edges { node { id } } }
    workfiles(sortBy: $sortBy) { edges { node { id } } }
    entityLists(sortBy: $sortBy) {
      edges { node { id items(sortBy: $sortBy) { edges { node { id } } } } }
    }
  }
}
"""


def test_legacy_query_validates_against_schema():
    schema = graphql_router.schema._schema  # type: ignore[attr-defined]
    document = parse(LEGACY_QUERY)
    assert validate(schema, document)  # fails without the rewrite

    document, count = rewrite_legacy_sort_by_variables(document)
    assert count == 1
    assert validate(schema, document) == []


def test_legacy_query_with_legacy_attrib_selection():
    """Both compatibility rewrites apply to the same query"""
    schema = graphql_router.schema._schema  # type: ignore[attr-defined]
    query = """
    query Legacy($projectName: String!, $sortBy: String) {
      project(name: $projectName) {
        tasks(sortBy: $sortBy) {
          edges { node { id attrib { fps width: resolutionWidth } } }
        }
      }
    }
    """
    query, attrib_count = rewrite_legacy_attrib_selections(query)
    assert attrib_count == 1
    document, sort_by_count = rewrite_legacy_sort_by_variables(parse(query))
    assert sort_by_count == 1
    assert validate(schema, document) == []


@strawberry.type
class Query:
    @strawberry.field
    def tasks(self, sort_by: list[str] | None = None) -> str:
        return ",".join(sort_by or [])


schema = strawberry.Schema(query=Query, extensions=[LegacySortByVariables])


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
    assert get_sort_keys(None) == []
    assert get_sort_keys([]) == []
    assert get_sort_keys("name") == ["name"]
    assert get_sort_keys(["status", "name", "status"]) == ["status", "name"]


def test_with_tiebreakers():
    assert with_tiebreakers(["a"], "path", "name") == ["a", "path", "name"]
    assert with_tiebreakers(["path", "name"], "path", "name") == ["path", "name"]
    assert with_tiebreakers(["name", "a"], "path", "name") == ["name", "a", "path"]
