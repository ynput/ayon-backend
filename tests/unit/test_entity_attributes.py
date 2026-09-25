"""Attribute values of entities: validation on save, stored values on load.

Uses the default attributes (see conftest.py), e.g. `fps` (float) and
`resolutionWidth` (integer, gt=0).
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from ayon_server.attributes.fix_attribute_values import invalid_values
from ayon_server.attributes.models import AttributeData
from ayon_server.attributes.validate_attribute_data import validate_attribute_data
from ayon_server.entities import (
    FolderEntity,
    ProjectEntity,
    TaskEntity,
    UserEntity,
    VersionEntity,
)
from ayon_server.entities.core.attrib import resolve_attrib
from ayon_server.entities.models.generator import generate_model
from ayon_server.exceptions import BadRequestException
from ayon_server.graphql.utils import process_attrib_data
from ayon_server.helpers.get_entity_class import get_entity_class

FOLDER = {"name": "shot010", "folder_type": "Shot"}
MANAGER: Any = SimpleNamespace(is_guest=False, is_manager=True)


#
# Loading: stored values are used as they are
#


class TestLoading:
    """Entities loaded from the database (exists=True).

    Values were validated when they were written, so they are used
    as they are stored (see fix_attribute_values for definition changes).
    """

    def test_stored_values(self):
        payload = {**FOLDER, "attrib": {"fps": 25.0, "resolutionWidth": 1920}}
        folder = FolderEntity("project", payload, exists=True)
        assert folder.attrib.fps == 25.0
        assert folder.attrib.resolutionWidth == 1920
        assert sorted(folder.own_attrib) == ["fps", "resolutionWidth"]

    def test_stored_values_are_not_validated(self):
        payload = {**FOLDER, "attrib": {"resolutionWidth": 0}}
        folder = FolderEntity("project", payload, exists=True)
        assert folder.attrib.resolutionWidth == 0
        assert folder.own_attrib == ["resolutionWidth"]

    def test_undefined_attributes_are_dropped(self):
        payload = {**FOLDER, "attrib": {"fps": 25, "removedAttribute": 1}}
        folder = FolderEntity("project", payload, exists=True)
        assert "removedAttribute" not in folder.attrib
        assert folder.own_attrib == ["fps"]

    def test_inheritance(self):
        payload = {**FOLDER, "attrib": {"resolutionWidth": 1920, "fps": None}}
        folder = FolderEntity(
            "project",
            payload,
            exists=True,
            inherited_attrib={"fps": 24.0, "resolutionWidth": 2048},
            project_attrib={"fps": 30.0, "resolutionHeight": 858},
        )
        assert folder.attrib.fps == 24.0  # parents (own value is None)
        assert folder.attrib.resolutionWidth == 1920  # own
        assert folder.attrib.resolutionHeight == 858  # project
        assert folder.attrib.pixelAspect == 1.0  # project attribute default
        assert folder.own_attrib == ["resolutionWidth"]
        # what the folder inherits (also for the attributes set on it)
        assert folder.inherited_attrib["resolutionWidth"] == 2048

    def test_no_inheritance(self):
        payload = {
            "name": "v001",
            "version": 1,
            "product_id": "a" * 32,
            "attrib": {"resolutionWidth": 2048},
        }
        version = VersionEntity(
            "project", payload, exists=True, inherited_attrib={"fps": 24.0}
        )
        assert version.attrib.fps is None
        assert version.attrib.resolutionWidth == 2048
        assert version.own_attrib == ["resolutionWidth"]

    def test_project_defaults(self):
        payload = {"name": "test", "code": "tst", "attrib": {"fps": 30.0}}
        project = ProjectEntity(payload, exists=True)
        assert project.attrib.fps == 30.0
        assert project.attrib.priority == "normal"  # default
        assert project.own_attrib == ["fps"]

    def test_top_level_entity(self):
        user = UserEntity({"name": "someone", "attrib": {"email": "a@b.c"}}, True)
        assert user.attrib.email == "a@b.c"
        assert user.attrib.fullName is None
        assert user.dict(exclude_none=True)["attrib"] == {"email": "a@b.c"}

    def test_task_without_inherited_attributes(self):
        record = {
            "id": "a" * 32,
            "name": "comp",
            "folder_id": "b" * 32,
            "folder_path": "sq01/sh010",
            "attrib": {},
            "inherited_attrib": None,
        }
        assert TaskEntity.preprocess_record(record)["path"] == "/sq01/sh010/comp"


class TestResolveAttrib:
    """Rules not covered by loading the entities (see TestLoading)"""

    def test_only_inheritable_values_are_inherited(self):
        resolved = resolve_attrib("folder", {}, project={"description": "project"})
        assert "description" not in resolved.values

    def test_undefined_inherited_values_are_dropped(self):
        resolved = resolve_attrib("task", {}, inherited={"removedAttribute": 1})
        assert "removedAttribute" not in resolved.values

    def test_unknown_entity_types(self):
        values = {"fps": "abc"}
        assert resolve_attrib("unknown", values).values == values


class TestGraphQL:
    """GraphQL resolves the values the same way as REST"""

    def test_same_as_rest(self):
        own = {"fps": 24.0, "resolutionWidth": 0, "removedAttribute": 1}
        inherited = {"fps": 25.0, "resolutionHeight": 858}
        project = {"pixelAspect": 2.0, "frameStart": None}
        resolved = resolve_attrib("folder", own, inherited=inherited, project=project)
        graphql = process_attrib_data(resolved.values, user=MANAGER)
        rest = FolderEntity(
            "project",
            {**FOLDER, "attrib": own},
            exists=True,
            inherited_attrib=inherited,
            project_attrib=project,
        )
        assert graphql == rest.dict(exclude_none=True)["attrib"]

    def test_list_item_datetimes_are_converted(self):
        result = process_attrib_data(
            {"reviewNote": "ok", "reviewedAt": "2024-01-01T10:00:00+00:00"},
            user=MANAGER,
            list_attribute_config={"reviewNote": "string", "reviewedAt": "datetime"},
        )
        assert result["reviewNote"] == "ok"
        assert result["reviewedAt"].year == 2024


#
# Saving: values are validated
#


class TestSaving:
    def test_new_entities_are_strict(self):
        with pytest.raises(ValidationError):
            FolderEntity("project", {**FOLDER, "attrib": {"fps": "abc"}})
        with pytest.raises(ValidationError):
            FolderEntity.model.post_model(**FOLDER, attrib={"resolutionWidth": -5})

    def test_valid_values_are_converted(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        assert folder.validated_attrib({"fps": "25", "resolutionWidth": 1920}) == {
            "fps": 25.0,
            "resolutionWidth": 1920,
        }

    def test_values_set_by_code_are_validated(self):
        # Values assigned to entity.attrib are not validated until saved
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        folder.attrib.fps = "abc"
        folder.own_attrib.append("fps")
        with pytest.raises(BadRequestException, match="fps"):
            folder.own_attrib_to_save()

    def test_none_values_are_not_saved(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {"fps": 25}})
        folder.attrib.fps = None
        assert folder.own_attrib_to_save() == {}

    def test_undefined_attributes_are_dropped(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        assert folder.validated_attrib({"removedAttribute": 1}) == {}


def test_invalid_values():
    # Used by fix_attribute_values after attribute definitions change
    values = {"fps": "abc", "resolutionWidth": 0, "frameStart": 1001, "gone": 1}
    model = FolderEntity.model.attrib_model
    assert set(invalid_values(model, values)) == {"fps", "resolutionWidth"}


#
# Attribute definitions
#


class TestAttributeDefinitions:
    def test_zero_limits_are_applied(self):
        model = generate_model(
            "Test",
            [
                {"name": "positive", "type": "integer", "title": "P", "gt": 0},
                {"name": "notNegative", "type": "float", "title": "N", "ge": 0},
            ],
        )
        with pytest.raises(ValidationError):
            model(positive=0)
        with pytest.raises(ValidationError):
            model(notNegative=-0.5)
        assert model(positive=1, notNegative=0).positive == 1

    def test_invalid_default_is_rejected(self):
        validate_attribute_data(
            "rating", AttributeData(type="integer", title="Rating", default=3, ge=0)
        )
        with pytest.raises(BadRequestException, match="Default value"):
            validate_attribute_data(
                "rating",
                AttributeData(type="integer", title="Rating", default=-1, ge=0),
            )

    @pytest.mark.parametrize("name", ["model_config", "model_dump", "json"])
    def test_reserved_attribute_names(self, name):
        with pytest.raises(BadRequestException, match="reserved"):
            validate_attribute_data(name, AttributeData(type="string", title="X"))

        # stored attributes with such names are skipped (no crash)
        model = generate_model(
            "Test",
            [
                {"name": name, "type": "string", "title": "X"},
                {"name": "ok", "type": "string", "title": "OK"},
            ],
        )
        assert list(model.model_fields) == ["ok"]


#
# Entity types
#


def test_get_entity_class():
    assert get_entity_class("folder") is FolderEntity
    assert get_entity_class("project") is ProjectEntity
    assert get_entity_class("user") is UserEntity
    with pytest.raises(ValueError):
        get_entity_class("unknown")


def test_project_actions_have_no_entities():
    from ayon_server.actions.context import ActionContext

    context = ActionContext(
        project_name="project", entity_type="project", entity_ids=["project"]
    )
    assert asyncio.run(context.get_entities()) == []
