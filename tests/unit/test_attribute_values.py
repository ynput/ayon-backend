"""ayon_server.attributes.values (default attributes, see conftest.py)"""

import pytest
from pydantic import ValidationError

from ayon_server.attributes.values import (
    invalid_attrib,
    resolve_attrib,
    validate_attrib,
)


def test_invalid_attrib():
    values = {"fps": "abc", "resolutionWidth": 0, "frameStart": 1001, "gone": 1}
    invalid = invalid_attrib("folder", values)
    assert set(invalid) == {"fps", "resolutionWidth"}


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
        )
        assert resolved.values["fps"] == 24.0  # own
        assert resolved.values["frameStart"] == 1  # None is not set
        assert resolved.values["resolutionWidth"] == 2048  # parents
        assert resolved.values["resolutionHeight"] == 858  # project
        assert resolved.values["pixelAspect"] == 1.0  # definition default
        assert resolved.own == ["fps"]
        # what the entity inherits (also for the attributes set on it)
        assert resolved.inherited["fps"] == 25

    def test_stored_values_are_not_validated(self):
        resolved = resolve_attrib(
            "task",
            {"resolutionWidth": 0, "removedAttribute": 1},
            inherited={"fps": "xyz", "resolutionWidth": 1920},
        )
        assert resolved.values["fps"] == "xyz"
        assert resolved.values["resolutionWidth"] == 0
        assert "removedAttribute" not in resolved.values
        assert resolved.own == ["resolutionWidth"]

    def test_only_inheritable_values_are_inherited(self):
        resolved = resolve_attrib("folder", {}, project={"description": "project"})
        assert "description" not in resolved.values

    def test_no_inheritance(self):
        resolved = resolve_attrib(
            "version",
            {"fps": 24.0},
            inherited={"resolutionWidth": 2048},
        )
        assert resolved.values == {"fps": 24.0}
        assert resolved.inherited == {}


class TestDefaults:
    """Defaults are applied once (resolve_attrib), for REST and GraphQL"""

    def test_project_defaults(self):
        resolved = resolve_attrib("project", {"fps": 30.0})
        assert resolved.values["fps"] == 30.0
        assert resolved.values["priority"] == "normal"  # default
        assert resolved.own == ["fps"]

    def test_no_defaults_for_other_entity_types(self):
        # Only project attributes have defaults, folders and tasks inherit them
        assert resolve_attrib("version", {}).values == {}

    def test_graphql_matches_rest(self):
        from types import SimpleNamespace

        from ayon_server.entities import ProjectEntity
        from ayon_server.graphql.utils import process_attrib_data

        user = SimpleNamespace(is_guest=False, is_manager=True)
        graphql = process_attrib_data("project", {"fps": 30.0}, user=user)  # type: ignore
        rest = ProjectEntity(
            {"name": "test", "code": "tst", "attrib": {"fps": 30.0}}, exists=True
        ).attrib
        assert graphql == {k: v for k, v in rest.items() if v is not None}


class TestEntityTypes:
    def test_get_entity_class(self):
        from ayon_server.entities import FolderEntity, ProjectEntity, UserEntity
        from ayon_server.helpers.get_entity_class import get_entity_class

        assert get_entity_class("folder") is FolderEntity
        assert get_entity_class("project") is ProjectEntity
        assert get_entity_class("user") is UserEntity
        with pytest.raises(ValueError):
            get_entity_class("unknown")

    def test_unknown_entity_types(self):
        values = {"fps": "abc"}
        assert invalid_attrib("unknown", values) == {}
        assert resolve_attrib("unknown", values).values == values


def test_project_actions_have_no_entities():
    import asyncio

    from ayon_server.actions.context import ActionContext

    context = ActionContext(
        project_name="project", entity_type="project", entity_ids=["project"]
    )
    assert asyncio.run(context.get_entities()) == []
