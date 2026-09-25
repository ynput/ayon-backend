"""ayon_server.attributes.values (default attributes, see conftest.py)"""

import pytest
from pydantic import ValidationError

from ayon_server.attributes.values import (
    invalid_attrib,
    resolve_attrib,
    valid_attrib,
    validate_attrib,
)


def test_invalid_attrib():
    values = {"fps": "abc", "resolutionWidth": 0, "frameStart": 1001, "gone": 1}
    invalid = invalid_attrib("folder", values)
    assert set(invalid) == {"fps", "resolutionWidth"}


def test_valid_attrib_keeps_values_unchanged():
    values = {"fps": "25", "frameStart": 1001, "resolutionWidth": 0, "gone": 1}
    assert valid_attrib("folder", values, label="test") == {
        "fps": "25",
        "frameStart": 1001,
    }


def test_validate_attrib():
    assert dict(validate_attrib("folder", {"fps": "25"}, partial=True)) == {"fps": 25.0}
    with pytest.raises(ValidationError):
        validate_attrib("folder", {"fps": "abc"}, partial=True)


class TestResolveAttrib:
    def test_layers(self):
        resolved = resolve_attrib(
            "folder",
            {"fps": 24.0, "frameStart": None},
            inherited={"resolutionWidth": 2048, "frameStart": 1},
            project={"resolutionWidth": 1024, "resolutionHeight": 858},
            label="test",
        )
        assert resolved.values["fps"] == 24.0  # own
        assert resolved.values["frameStart"] == 1  # None is not set
        assert resolved.values["resolutionWidth"] == 2048  # parents
        assert resolved.values["resolutionHeight"] == 858  # project
        assert resolved.values["pixelAspect"] == 1.0  # definition default
        assert resolved.own == ["fps"]
        # what the entity inherits (also for the attributes set on it)
        assert resolved.inherited["fps"] == 25

    def test_invalid_values_fall_back(self):
        resolved = resolve_attrib(
            "task",
            {"fps": "abc"},
            inherited={"fps": "xyz"},
            project={"fps": 30.0},
            label="test",
        )
        assert resolved.values["fps"] == 30.0
        assert resolved.own == []

    def test_no_inheritance(self):
        resolved = resolve_attrib(
            "version",
            {"fps": 24.0},
            inherited={"resolutionWidth": 2048},
            label="test",
        )
        assert resolved.values == {"fps": 24.0}
        assert resolved.inherited == {}
