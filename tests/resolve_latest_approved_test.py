import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.resolve.__init__ import get_version_conditions, parse_uri


def test_parse_uri_accepts_latest_approved_alias():
    parsed = parse_uri(
        "ayon+entity://myproject/assets/asset?product=renderMain&version=latestApproved"
    )

    assert parsed.version_name == "latestApproved"


def test_get_version_conditions_supports_latest_approved():
    conditions = get_version_conditions("latestApproved")

    assert len(conditions) == 1
    condition = conditions[0]
    assert "SELECT DISTINCT ON (product_id) id" in condition
    assert "lower(status) = 'approved'" in condition
    assert "ORDER BY product_id, version DESC" in condition


def test_get_version_conditions_normalizes_latest_approved_casing():
    assert get_version_conditions("LatestApproved") == get_version_conditions(
        "latestApproved"
    )
