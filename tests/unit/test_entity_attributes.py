"""Attribute values of entities: validation on save, tolerance on load.

Uses the default attributes (see conftest.py), e.g. `fps` (float) and
`resolutionWidth` (integer, gt=0).
"""

import pytest
from loguru import logger
from pydantic import ValidationError

from ayon_server.entities import FolderEntity, UserEntity, VersionEntity
from ayon_server.entities.models.generator import generate_model
from ayon_server.exceptions import BadRequestException

FOLDER = {"name": "shot010", "folder_type": "Shot"}


@pytest.fixture
def debug_log():
    messages: list[str] = []
    handler_id = logger.add(lambda m: messages.append(m.record["message"]), level=0)
    yield messages
    logger.remove(handler_id)


class TestConstraints:
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

    def test_default_attribute_constraint(self):
        with pytest.raises(ValidationError):
            FolderEntity.model.post_model(**FOLDER, attrib={"resolutionWidth": -5})


class TestLoading:
    """Entities loaded from the database (exists=True)"""

    def test_valid_values(self):
        payload = {**FOLDER, "attrib": {"fps": 25, "resolutionWidth": 1920}}
        folder = FolderEntity("project", payload, exists=True)
        assert folder.attrib.fps == 25.0
        assert folder.attrib.resolutionWidth == 1920
        assert sorted(folder.own_attrib) == ["fps", "resolutionWidth"]

    def test_invalid_values_are_ignored(self, debug_log):
        # Nothing is inherited: the default of the attribute definition is used
        payload = {**FOLDER, "attrib": {"fps": "abc", "resolutionWidth": 2048}}
        folder = FolderEntity("project", payload, exists=True)
        assert folder.attrib.fps == 25.0
        assert folder.attrib.resolutionWidth == 2048
        assert folder.own_attrib == ["resolutionWidth"]
        assert any("Ignoring invalid attribute fps=abc" in m for m in debug_log)

    def test_invalid_values_are_dropped_without_inheritance(self):
        # Versions do not inherit attributes
        payload = {
            "name": "v001",
            "version": 1,
            "product_id": "a" * 32,
            "attrib": {"fps": "abc", "resolutionWidth": 2048},
        }
        version = VersionEntity("project", payload, exists=True)
        assert version.attrib.fps is None
        assert version.attrib.resolutionWidth == 2048
        assert version.own_attrib == ["resolutionWidth"]

    def test_violated_constraints_are_ignored(self):
        payload = {**FOLDER, "attrib": {"resolutionWidth": 0}}
        folder = FolderEntity("project", payload, exists=True)
        assert folder.attrib.resolutionWidth == 1920  # the default
        assert folder.own_attrib == []

    def test_undefined_attributes_are_dropped(self):
        payload = {**FOLDER, "attrib": {"fps": 25, "removedAttribute": 1}}
        folder = FolderEntity("project", payload, exists=True)
        assert "removedAttribute" not in folder.attrib
        assert folder.own_attrib == ["fps"]

    def test_invalid_values_fall_back_to_inherited(self):
        # e.g. an invalid own value of a folder, whose parent sets it
        payload = {**FOLDER, "attrib": {"fps": "abc", "resolutionWidth": 1920}}
        folder = FolderEntity(
            "project",
            payload,
            exists=True,
            inherited_attrib={"fps": 24.0, "resolutionWidth": 2048},
        )
        assert folder.attrib.fps == 24.0
        assert folder.attrib.resolutionWidth == 1920
        assert folder.own_attrib == ["resolutionWidth"]

    def test_invalid_inherited_values_fall_back_to_project(self):
        # inherited values are exported from the parents, which may be invalid too
        payload = {**FOLDER, "attrib": {"fps": "abc"}}
        folder = FolderEntity(
            "project",
            payload,
            exists=True,
            inherited_attrib={"fps": "xyz"},
            project_attrib={"fps": 30.0},
        )
        assert folder.attrib.fps == 30.0
        assert folder.own_attrib == []

    def test_top_level_entity(self):
        payload = {"name": "someone", "attrib": {"email": 42, "fullName": ["x"]}}
        user = UserEntity(payload, exists=True)
        assert user.attrib.email == "42"  # numbers are accepted by strings
        assert user.attrib.fullName is None

    def test_new_entities_are_strict(self):
        with pytest.raises(ValidationError):
            FolderEntity("project", {**FOLDER, "attrib": {"fps": "abc"}})


class TestSaving:
    """Values set by code are validated before saving"""

    def test_valid_values_are_converted(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        assert folder.validated_attrib({"fps": "25", "resolutionWidth": 1920}) == {
            "fps": 25.0,
            "resolutionWidth": 1920,
        }

    def test_invalid_values_are_rejected(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        folder.attrib.fps = "abc"
        with pytest.raises(BadRequestException, match="fps"):
            folder.validated_attrib({"fps": folder.attrib.fps})

    def test_undefined_attributes_are_dropped(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        assert folder.validated_attrib({"removedAttribute": 1}) == {}


class TestAttributeDefinitions:
    def test_invalid_default_is_rejected(self):
        from ayon_server.attributes.models import AttributeData
        from ayon_server.attributes.validate_attribute_data import (
            validate_attribute_data,
        )

        validate_attribute_data(
            "rating", AttributeData(type="integer", title="Rating", default=3, ge=0)
        )
        with pytest.raises(BadRequestException, match="Default value"):
            validate_attribute_data(
                "rating",
                AttributeData(type="integer", title="Rating", default=-1, ge=0),
            )


class TestReviewFixes:
    def test_folder_save_validates_attributes(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {}})
        folder.attrib.fps = "abc"
        folder.own_attrib.append("fps")
        with pytest.raises(BadRequestException, match="fps"):
            folder.own_attrib_to_save()

    def test_own_attrib_to_save_skips_none(self):
        folder = FolderEntity("project", {**FOLDER, "attrib": {"fps": 25}})
        folder.attrib.fps = None
        assert folder.own_attrib_to_save() == {}

    def test_task_without_inherited_attributes(self):
        from ayon_server.entities import TaskEntity

        record = {
            "id": "a" * 32,
            "name": "comp",
            "folder_id": "b" * 32,
            "folder_path": "sq01/sh010",
            "attrib": {},
            "inherited_attrib": None,
        }
        assert TaskEntity.preprocess_record(record)["path"] == "/sq01/sh010/comp"

    @pytest.mark.parametrize("name", ["model_config", "model_dump", "json"])
    def test_reserved_attribute_names(self, name):
        from ayon_server.attributes.models import AttributeData
        from ayon_server.attributes.validate_attribute_data import (
            validate_attribute_data,
        )

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

    def test_validate_does_not_modify_the_source_model(self):
        from ayon_server.models.attrib_values import AttribValues

        source_model = generate_model(
            "Source",
            [
                {"name": "fps", "type": "float", "title": "FPS"},
                {"name": "removed", "type": "string", "title": "Removed"},
            ],
        )
        source = source_model(fps=25, removed="x")
        AttribValues(lambda: FolderEntity.model.attrib_model).validate(source)
        assert source.model_fields_set == {"fps", "removed"}
