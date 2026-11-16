import pytest

from ayon_server.graphql.resolvers.common import HasLinksFilter, get_has_links_conds


@pytest.mark.parametrize("value", list(HasLinksFilter))
def test_every_has_links_value_builds_conditions(value: HasLinksFilter) -> None:
    conds = get_has_links_conds("test", "tasks.id", value)
    assert conds
    assert all("project_test.links" in cond for cond in conds)
