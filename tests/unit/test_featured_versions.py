"""SQL built for the featured version of a product.

Running it in Postgres is tested in tests/integration/test_featured_versions.py
"""

import pytest

from ayon_server.exceptions import BadRequestException
from ayon_server.graphql.resolvers.featured_versions import (
    featured_version_id_expression,
)


def test_single_flag_is_one_subquery():
    expr = featured_version_id_expression("demo", ["latestDone"], "e")
    assert not expr.startswith("COALESCE")
    assert "project_demo.statuses" in expr
    assert "e.product_id" in expr


def test_flags_keep_their_priority_order():
    expr = featured_version_id_expression("demo", ["hero", "latest"], "e")
    assert expr.startswith("COALESCE(")
    assert expr.index("h.version < 0") < expr.index("ORDER BY v.creation_order")


@pytest.mark.parametrize("flags", [[], ["newest"], ["latest", "heroOnly"]])
def test_invalid_flags_are_rejected(flags):
    with pytest.raises(BadRequestException):
        featured_version_id_expression("demo", flags, "e")
