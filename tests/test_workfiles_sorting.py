"""Unit tests for workfiles sorting / pagination (no database required).

The `ayon_server.graphql` package builds its strawberry schema on import,
which requires the attribute library loaded from the database. To keep these
tests DB-free, the packages are replaced with bare namespace modules and the
node/connection modules the resolver imports are stubbed out.
"""

import asyncio
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.append(ROOT)


def _load_resolver_modules():
    saved = {}

    def stub(name, module):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module

    for pkg in ("ayon_server.graphql", "ayon_server.graphql.resolvers"):
        m = types.ModuleType(pkg)
        m.__path__ = [os.path.join(ROOT, *pkg.split("."))]
        stub(pkg, m)

    for name in (
        "ayon_server.graphql.connections",
        "ayon_server.graphql.edges",
        "ayon_server.graphql.nodes",
        "ayon_server.graphql.nodes.workfile",
        "ayon_server.graphql.resolvers.common",
        "ayon_server.graphql.types",
    ):
        stub(name, MagicMock())

    try:
        from ayon_server.graphql.resolvers import pagination, workfiles

        return pagination, workfiles
    finally:
        # Do not leak the stubs into other tests
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        sys.modules.pop("ayon_server.graphql.resolvers.workfiles", None)
        sys.modules.pop("ayon_server.graphql.resolvers.pagination", None)
        sys.modules.pop("ayon_server.graphql.resolvers.sorting", None)


pagination, workfiles = _load_resolver_modules()
BadRequestException = workfiles.BadRequestException


def order_by(sort_by):
    return asyncio.run(workfiles.get_workfiles_order_by(sort_by))


class TestWorkfilesOrderBy:
    def test_default(self):
        assert order_by(None) == ["workfiles.creation_order"]

    def test_no_nonexistent_name_column(self):
        # workfiles table has no `name` column
        for exp in workfiles.SORT_OPTIONS.values():
            assert "workfiles.name" not in exp

    def test_name_sorts_by_file_name_part_of_path(self):
        ob = order_by("name")
        assert ob == [workfiles.WORKFILE_NAME_EXPRESSION, "workfiles.creation_order"]
        assert "workfiles.path" in ob[0]
        # Both separators must be excluded from the file name,
        # the backslash must be escaped for the POSIX regex bracket
        assert r"[^/\\]*$" in ob[0]

    def test_path(self):
        assert order_by("path") == ["workfiles.path", "workfiles.creation_order"]

    def test_status(self):
        assert order_by("status") == ["workfiles.status", "workfiles.creation_order"]

    def test_attrib(self):
        ob = order_by("attrib.someAttribute")
        assert ob[0] == "workfiles.attrib->>'someAttribute'"
        assert ob[-1] == "workfiles.creation_order"

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
    def test_attrib_injection_rejected(self, sort_by):
        with pytest.raises(BadRequestException):
            order_by(sort_by)

    def test_unknown_sort_key(self):
        with pytest.raises(BadRequestException):
            order_by("nonexistent")


class TestWorkfilesPagination:
    def test_name_cursor_is_compared_as_text(self):
        # A file name that looks like a timestamp must not be cast
        # to timestamptz in the cursor condition
        ob = order_by("name")
        cursor = pagination.encode_cursor(["2024-01-01T10.ma", 5])
        _, conds, _ = pagination.create_pagination(ob, first=10, after=cursor)
        assert "timestamptz" not in conds
        assert conds == (
            f"({workfiles.WORKFILE_NAME_EXPRESSION}, workfiles.creation_order)"
            " > ('2024-01-01T10.ma'::text, 5)"
        )

    def test_name_cursor_escapes_quotes(self):
        ob = order_by("name")
        cursor = pagination.encode_cursor(["it's.ma", 5])
        _, conds, _ = pagination.create_pagination(ob, first=10, after=cursor)
        assert "'it''s.ma'::text" in conds

    @pytest.mark.parametrize("sort_by", ["status", "name", "path"])
    def test_ordering_and_cursor_columns(self, sort_by):
        ob = order_by(sort_by)
        ordering, conds, cursor = pagination.create_pagination(ob, first=2)
        assert conds == ""
        assert ordering == (
            f"ORDER BY {ob[0]} ASC, workfiles.creation_order ASC LIMIT 4"
        )
        assert cursor == (
            f"{ob[0]} AS cursor_0, workfiles.creation_order AS cursor_1"
        )

    def test_status_cursor(self):
        ob = order_by("status")
        cursor = pagination.encode_cursor(["In progress", 3])
        _, conds, _ = pagination.create_pagination(ob, last=2, before=cursor)
        assert conds == (
            "(workfiles.status, workfiles.creation_order)"
            " < ('In progress'::text, 3)"
        )
