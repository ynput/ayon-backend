import pytest
from pydantic import BaseModel, ValidationError

from ayon_server.models import RestField, RestModel
from ayon_server.models.field_info import get_field_extra, translate_field_kwargs
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.pydantic_compat import Field as CompatField


class Sub(BaseModel):
    a: int = 1


class Item(RestModel):
    name: str
    count: int = 0
    data: dict = RestField(default_factory=dict)
    tags: list[str] = RestField(default_factory=list)


class TestPydantic1Coercion:
    def test_valid_data(self):
        item = Item(name="x", count=2, data={"a": 1}, tags=["t"])
        assert item.model_dump() == {
            "name": "x",
            "count": 2,
            "data": {"a": 1},
            "tags": ["t"],
        }

    def test_coercion(self):
        item = Item(name=True, count=2.7, data=Sub(), tags=[True, "t"])
        assert item.name == "True"
        assert item.count == 2
        assert item.data == {"a": 1}
        assert item.tags == ["True", "t"]

    def test_numbers_to_str(self):
        assert Item(name=5).name == "5"

    def test_invalid_data(self):
        with pytest.raises(ValidationError):
            Item(name="x", count="abc")

    def test_nested_models(self):
        class Parent(RestModel):
            items: list[Item]

        parent = Parent(items=[{"name": True, "count": 1.5}])
        assert parent.items[0].name == "True"
        assert parent.items[0].count == 1

    def test_settings_model(self):
        class Settings(BaseSettingsModel):
            name: str = SettingsField("")
            count: int = SettingsField(0)

        settings = Settings(name=False, count=3.9)
        assert settings.name == "False"
        assert settings.count == 3


class TestConfig:
    def test_rest_model_config(self):
        config = RestModel.model_config
        assert config["alias_generator"] is not None
        assert config["coerce_numbers_to_str"]
        assert config["from_attributes"]

    def test_settings_model_config(self):
        config = BaseSettingsModel.model_config
        assert "alias_generator" not in config
        assert config["coerce_numbers_to_str"]
        assert config["from_attributes"]


class TestTranslateFieldKwargs:
    def test_pydantic1_arguments(self):
        kwargs, extra = translate_field_kwargs(
            [],
            {
                "regex": "^a$",
                "min_items": 1,
                "max_items": 3,
                "allow_mutation": False,
                "unique_items": True,
                "example": "x",
                "title": None,
            },
        )
        assert kwargs == {
            "pattern": "^a$",
            "min_length": 1,
            "max_length": 3,
            "frozen": True,
            "examples": ["x"],
        }
        assert extra == {"uniqueItems": True}

    def test_pydantic2_arguments_take_precedence(self):
        kwargs, _ = translate_field_kwargs(
            None,
            {"regex": "^a$", "pattern": "^b$", "min_items": 1, "min_length": 2},
        )
        assert kwargs == {"pattern": "^b$", "min_length": 2}

    def test_examples_merged(self):
        kwargs, _ = translate_field_kwargs(None, {"examples": ["a"], "example": "b"})
        assert kwargs == {"examples": ["a", "b"]}

    def test_const(self):
        _, extra = translate_field_kwargs("value", {"const": True})
        assert extra == {"const": "value"}


class TestFieldFunctions:
    @pytest.mark.parametrize("field", [RestField, SettingsField, CompatField])
    def test_same_constraints(self, field):
        info = field("x", regex="^[a-z]+$", min_length=1, example="abc")
        metadata = {type(m).__name__: m for m in info.metadata}
        assert metadata["_PydanticGeneralMetadata"].pattern == "^[a-z]+$"
        assert metadata["MinLen"].min_length == 1
        assert info.examples == ["abc"]

    def test_unknown_arguments(self):
        # RestField and SettingsField drop unknown arguments (as in Pydantic 1),
        # Pydantic 1 Field stored them in the extra
        assert "whatever" not in get_field_extra(RestField("x", whatever=1))
        assert "whatever" not in get_field_extra(SettingsField("x", whatever=1))
        assert get_field_extra(CompatField("x", whatever=1))["whatever"] == 1

    def test_rest_field_deprecated(self):
        assert get_field_extra(RestField("x", deprecated=True)) == {"deprecated": True}


class TestV1Fields:
    @pytest.mark.parametrize("model_type", ["rest", "settings"])
    def test_class_and_instance_access(self, model_type):
        if model_type == "rest":

            class Model(RestModel):
                name: str = RestField("x", title="Name")

        else:

            class Model(BaseSettingsModel):
                name: str = SettingsField("x", title="Name", scope=["studio"])

        for obj in (Model, Model()):
            field = obj.__fields__["name"]
            assert type(field).__name__ == "V1ModelField"
            assert field.type_ is str
            assert field.default == "x"
            assert field.field_info.title == "Name"

        extra = Model.__fields__["name"].field_info.extra
        if model_type == "settings":
            assert extra["scope"] == ["studio"]
