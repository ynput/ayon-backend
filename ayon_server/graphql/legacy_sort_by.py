"""Backwards compatibility for `String` typed `sortBy` variables.

The `sortBy` argument of the entity resolvers used to be a single `String`.
It is now `[String!]`, where the keys are applied in order of precedence.

Inline values need no special handling. GraphQL input coercion wraps
a single value in a list, so `sortBy: "name"` is the same as `sortBy: ["name"]`.

Variables are a different story. Older clients declare the variable as

    query Tasks($sortBy: String) { project(name: "x") { tasks(sortBy: $sortBy) } }

and such a query fails validation, because a `String` variable cannot be used
where `[String!]` is expected. After the query is parsed, such declarations
are rewritten to `[String!]` (`String!` becomes `[String!]!`).
The variable value itself needs no change: a single string passed
for a list typed variable is wrapped in a list during coercion.

Only variables used exclusively as `sortBy` arguments are rewritten, so a
variable which is also passed to another `String` argument keeps its type.
"""

from collections.abc import Iterator
from typing import Any

from graphql import (
    ArgumentNode,
    DocumentNode,
    ListTypeNode,
    NamedTypeNode,
    NonNullTypeNode,
    TypeNode,
    VariableDefinitionNode,
    VariableNode,
    Visitor,
    visit,
)
from strawberry.extensions import SchemaExtension

from ayon_server.logging import logger

SORT_BY_ARGUMENT = "sortBy"


def _as_string_list(type_node: TypeNode) -> TypeNode | None:
    """Return `[String!]` type for `String` (`[String!]!` for `String!`).

    Returns None if the type is not a (non-null) `String`.
    """
    non_null = isinstance(type_node, NonNullTypeNode)
    named = type_node.type if non_null else type_node  # type: ignore[attr-defined]
    if not isinstance(named, NamedTypeNode) or named.name.value != "String":
        return None
    list_type: TypeNode = ListTypeNode(type=NonNullTypeNode(type=named))
    return NonNullTypeNode(type=list_type) if non_null else list_type


class _VariableUsageCollector(Visitor):
    def __init__(self) -> None:
        super().__init__()
        self.sort_by: set[str] = set()
        self.other: set[str] = set()

    def enter_variable(self, node: VariableNode, _key, parent, *_args) -> None:
        if isinstance(parent, VariableDefinitionNode):
            return  # declaration, not a usage
        if isinstance(parent, ArgumentNode) and parent.name.value == SORT_BY_ARGUMENT:
            self.sort_by.add(node.name.value)
        else:
            self.other.add(node.name.value)


class _VariableTypeRewriter(Visitor):
    def __init__(self, names: set[str]) -> None:
        super().__init__()
        self.names = names
        self.count = 0

    def enter_variable_definition(self, node: VariableDefinitionNode, *_args) -> Any:
        if node.variable.name.value not in self.names:
            return None
        new_type = _as_string_list(node.type)
        if new_type is None:
            return None
        self.count += 1
        return VariableDefinitionNode(
            variable=node.variable,
            type=new_type,
            default_value=node.default_value,
            directives=node.directives,
        )


def rewrite_legacy_sort_by_variables(
    document: DocumentNode,
) -> tuple[DocumentNode, int]:
    """Rewrite `String` typed variables used as `sortBy` to `[String!]`

    Returns the new document and the number of rewritten variable definitions.
    """
    collector = _VariableUsageCollector()
    visit(document, collector)
    names = collector.sort_by - collector.other
    if not names:
        return document, 0

    rewriter = _VariableTypeRewriter(names)
    new_document = visit(document, rewriter)
    return new_document, rewriter.count


class LegacySortByVariables(SchemaExtension):
    """Rewrite `String` typed `sortBy` variables of older clients after parsing."""

    def on_parse(self) -> Iterator[None]:
        yield
        ctx = self.execution_context
        if ctx.graphql_document is None or SORT_BY_ARGUMENT not in (ctx.query or ""):
            return
        document, count = rewrite_legacy_sort_by_variables(ctx.graphql_document)
        if count:
            ctx.graphql_document = document
            logger.trace(
                f"Rewrote {count} legacy sortBy variable(s) "
                f"in {ctx.operation_name or 'unnamed'} query"
            )
