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


class TestStoredValues:
    """GraphQL follows the same rules as REST (see test_entity_attributes.py)"""

    def test_same_as_rest(self):
        from ayon_server.entities import FolderEntity

        own = {"fps": 24.0, "resolutionWidth": 0, "removedAttribute": 1}
        inherited = {"fps": 25.0, "resolutionHeight": 858}
        project = {"pixelAspect": 2.0, "frameStart": None}
        graphql = process_attrib_data(
            "folder",
            own,
            user=MANAGER,
            inherited_attrib=inherited,
            project_attrib=project,
        )
        rest = FolderEntity(
            "project",
            {"name": "shot010", "folder_type": "Shot", "attrib": own},
            exists=True,
            inherited_attrib=inherited,
            project_attrib=project,
        )
        assert graphql == rest.dict(exclude_none=True)["attrib"]
        assert graphql["resolutionWidth"] == 0  # stored values are not validated

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
