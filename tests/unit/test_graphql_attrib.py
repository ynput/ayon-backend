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
