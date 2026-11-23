import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ayon_server.sqlfilter import QueryCondition, QueryFilter, build_filter

FIELD_TYPES = {
    "ayon.2d.PixelBased": {1: {"display_window_width": "integer"}},
    "ayon.time.FrameRanged": {
        1: {"frame_start": "integer", "frames_per_second": "string"},
        2: {"frame_start": "integer", "frame_rate_numerator": "integer"},
    },
    "ayon.color.ColorManaged": {1: {"color_space": "string"}},
    "ayon.meta.Tagged": {1: {"tags": "list_of_strings"}},
    "ayon.time.Handles": {1: {"inclusive": "boolean"}},
}


def compile(key: str, operator: str, value=None, types=FIELD_TYPES) -> str:
    condition = {"key": key, "operator": operator}
    if value is not None:
        condition["value"] = value
    result = build_filter(
        QueryFilter(conditions=[QueryCondition(**condition)]),
        column_whitelist=["trait_fields", "trait_ids", "name"],
        table_prefix="r",
        trait_field_types=types,
    )
    assert result is not None
    return result


def test_eq_uses_containment():
    assert compile("traits/ayon.2d.PixelBased/display_window_width", "eq", 1920) == (
        """(r.trait_fields @> """
        """'{"ayon.2d.PixelBased.v1": {"display_window_width": 1920}}'::jsonb)"""
    )


def test_versionless_id_covers_versions_with_the_field():
    sql = compile("traits/ayon.time.FrameRanged/frame_start", "eq", 1001)
    assert '"ayon.time.FrameRanged.v1"' in sql
    assert '"ayon.time.FrameRanged.v2"' in sql
    assert " OR " in sql
    # only v2 has the field
    sql = compile("traits/ayon.time.FrameRanged/frame_rate_numerator", "eq", 24)
    assert '"ayon.time.FrameRanged.v1"' not in sql


def test_versioned_id_limits_to_the_version():
    sql = compile("traits/ayon.time.FrameRanged.v2/frame_start", "eq", 1001)
    assert '"ayon.time.FrameRanged.v1"' not in sql
    assert '"ayon.time.FrameRanged.v2"' in sql


def test_absence_operators_join_versions_with_and():
    sql = compile("traits/ayon.time.FrameRanged/frame_start", "isnull")
    assert " AND " in sql and " OR " not in sql
    sql = compile("traits/ayon.time.FrameRanged/frame_start", "notnull")
    assert " OR " in sql


def test_float_type_accepts_int():
    types = {"ayon.x.T": {1: {"value": "float"}}}
    assert '"value": 24' in compile("traits/ayon.x.T/value", "eq", 24, types)


def test_in_is_or_of_containments():
    sql = compile(
        "traits/ayon.color.ColorManaged/color_space", "in", ["ACEScg", "sRGB"]
    )
    assert sql.count("@>") == 2
    assert " OR " in sql


def test_list_field_includes():
    sql = compile("traits/ayon.meta.Tagged/tags", "eq", "hero")
    assert """{"tags": ["hero"]}""" in sql
    sql = compile("traits/ayon.meta.Tagged/tags", "includesany", ["a", "b"])
    assert sql.count("@>") == 2


def test_ne_requires_the_field():
    sql = compile("traits/ayon.2d.PixelBased/display_window_width", "ne", 1920)
    assert "IS NOT NULL" in sql and "NOT r.trait_fields @>" in sql


def test_range_and_text():
    sql = compile("traits/ayon.2d.PixelBased/display_window_width", "gte", 2048)
    assert "::numeric >= 2048" in sql
    sql = compile("traits/ayon.color.ColorManaged/color_space", "like", "aces")
    assert "ILIKE" in sql


def test_empty_list_is_missing_field():
    sql = compile("traits/ayon.meta.Tagged/tags", "eq", [])
    assert "IS NULL" in sql


def test_quotes_are_escaped():
    sql = compile("traits/ayon.color.ColorManaged/color_space", "eq", "it's")
    assert "it''s" in sql


def test_value_type_picks_versions():
    # v1 stores fps as a string, v2 has no such field: only v1 matches
    sql = compile("traits/ayon.time.FrameRanged/frames_per_second", "eq", "24")
    assert '"ayon.time.FrameRanged.v1"' in sql
    with pytest.raises(ValueError, match="Invalid value"):
        compile("traits/ayon.time.FrameRanged/frames_per_second", "eq", 24)


@pytest.mark.parametrize(
    "key",
    [
        "traits/ayon.unknown.Trait/x",
        "traits/ayon.2d.PixelBased/unknown",
        "traits/ayon.2d.PixelBased.v9/display_window_width",
        "traits/ayon.2d.PixelBased",
        "traits/ayon.2d.PixelBased/bad-field",
        "traits/ayon.2d.Pixel'Based/display_window_width",
    ],
)
def test_invalid_keys(key):
    with pytest.raises(ValueError):
        compile(key, "eq", 1)


def test_wrong_value_type():
    with pytest.raises(ValueError, match="Invalid value"):
        compile("traits/ayon.2d.PixelBased/display_window_width", "eq", "wide")
    with pytest.raises(ValueError, match="Invalid value"):
        compile("traits/ayon.time.Handles/inclusive", "eq", 1)


def test_requires_field_types():
    with pytest.raises(ValueError, match="not supported"):
        compile("traits/ayon.2d.PixelBased/display_window_width", "eq", 1, None)


def test_requires_whitelisted_column():
    with pytest.raises(ValueError):
        build_filter(
            QueryFilter(
                conditions=[
                    QueryCondition(
                        key="traits/ayon.2d.PixelBased/display_window_width",
                        operator="eq",
                        value=1,
                    )
                ]
            ),
            column_whitelist=["name"],
            trait_field_types=FIELD_TYPES,
        )


def test_trait_ids():
    assert compile("traitIds", "includesall", ["ayon.2d.PixelBased"]) == (
        "(r.trait_ids @> ARRAY['ayon.2d.PixelBased']::varchar[])"
    )
    assert "&&" in compile("traitIds", "includesany", ["a", "b"])
    assert compile("traitIds", "excludesany", ["a"]).startswith("(NOT ")


def test_other_columns_unchanged():
    assert "r.name" in compile("name", "eq", "x")
