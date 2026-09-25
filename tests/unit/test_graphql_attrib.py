from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.graphql.utils import process_attrib_data

MANAGER: Any = SimpleNamespace(is_guest=False, is_manager=True)


@pytest.mark.parametrize("entity_type", ["folder", "task"])
def test_inherited_attributes_do_not_change_own_attributes(entity_type):
    # ownAttrib of folder and task nodes lists the keys of their own
    # attributes, so resolving `attrib` / `allAttrib` must not add
    # inherited or project values to them
    own = {"fps": 24.0}
    result = process_attrib_data(
        entity_type,
        own,
        user=MANAGER,
        inherited_attrib={"resolutionWidth": 2048},
        project_attrib={"resolutionHeight": 858},
    )
    assert own == {"fps": 24.0}
    assert result["fps"] == 24.0
    assert result["resolutionWidth"] == 2048
    assert result["resolutionHeight"] == 858


def test_own_values_take_precedence():
    result = process_attrib_data(
        "folder",
        {"fps": 24.0},
        user=MANAGER,
        inherited_attrib={"fps": 25.0},
        project_attrib={"fps": 30.0},
    )
    assert result["fps"] == 24.0


class TestInvalidStoredValues:
    """GraphQL follows the same rules as REST (see test_entity_attributes.py)"""

    def test_invalid_own_value_falls_back_to_inherited(self):
        result = process_attrib_data(
            "folder",
            {"fps": "abc", "resolutionWidth": 1920},
            user=MANAGER,
            inherited_attrib={"fps": 24.0},
        )
        assert result["fps"] == 24.0
        assert result["resolutionWidth"] == 1920

    def test_invalid_inherited_value_falls_back_to_project(self):
        result = process_attrib_data(
            "folder",
            {},
            user=MANAGER,
            inherited_attrib={"fps": "abc"},
            project_attrib={"fps": 25.0},
        )
        assert result["fps"] == 25.0

    def test_undefined_attributes_are_dropped(self):
        result = process_attrib_data("version", {"removedAttribute": 1}, user=MANAGER)
        assert "removedAttribute" not in result

    def test_list_attributes_are_kept(self):
        result = process_attrib_data(
            "version",
            {"reviewNote": "ok"},
            user=MANAGER,
            list_attribute_config={"reviewNote": "string"},
        )
        assert result["reviewNote"] == "ok"
