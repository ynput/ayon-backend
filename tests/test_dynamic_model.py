import copy
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from ayon_server.models.dynamic_model import DynamicModel, get_dynamic_model
from ayon_server.models.field_info import (
    get_field_annotation,
    iter_annotation_types,
    strip_optional,
)


def make_attrib_model(**fields: type) -> type[BaseModel]:
    return create_model(  # type: ignore[call-overload,no-any-return]
        "ThingAttribModel",
        __config__=ConfigDict(coerce_numbers_to_str=True),
        **{name: (ftype | None, Field(None)) for name, ftype in fields.items()},
    )


class Registry:
    """Holds the current model, which may be replaced"""

    def __init__(self) -> None:
        self.model = make_attrib_model(fps=float)


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def thing_model(registry: Registry) -> tuple[type[BaseModel], DynamicModel]:
    attrib_type = DynamicModel(lambda: registry.model)

    class ThingModel(BaseModel):
        name: str
        attrib: attrib_type.annotation = Field(  # type: ignore[name-defined]
            default_factory=attrib_type,
            title="Thing attributes",
        )

    return ThingModel, attrib_type


def test_validation_follows_model_replacement(registry, thing_model):
    ThingModel, _ = thing_model

    thing = ThingModel(name="a", attrib={"fps": "25", "resX": 1})
    assert thing.attrib.fps == 25.0
    assert not hasattr(thing.attrib, "resX")

    # Replace the model. The parent model is not rebuilt.
    registry.model = make_attrib_model(fps=float, resX=int)

    thing = ThingModel(name="a", attrib={"fps": 25, "resX": "1"})
    assert thing.attrib.resX == 1
    assert type(thing.attrib) is registry.model

    with pytest.raises(ValidationError) as exc:
        ThingModel(name="a", attrib={"resX": "nope"})
    assert exc.value.errors()[0]["loc"] == ("attrib", "resX")


def test_subclass_follows_model_replacement(registry, thing_model):
    ThingModel, _ = thing_model

    class SubThingModel(ThingModel):  # type: ignore[valid-type,misc]
        extra: int = 1

    registry.model = make_attrib_model(resX=int)
    assert SubThingModel(name="a", attrib={"resX": "2"}).attrib.resX == 2


def test_instance_of_replaced_model(registry, thing_model):
    ThingModel, _ = thing_model
    old = ThingModel(name="a", attrib={"fps": 24})

    registry.model = make_attrib_model(fps=float, resX=int)

    # Instances of the previous model are converted (keeping fields_set)
    new = ThingModel(name="a", attrib=old.attrib)
    assert type(new.attrib) is registry.model
    assert new.attrib.fps == 24
    assert new.attrib.model_fields_set == {"fps"}

    # and instances of the previous model are still serializable
    assert old.model_dump() == {"name": "a", "attrib": {"fps": 24.0}}


def test_default_factory(registry, thing_model):
    ThingModel, _ = thing_model
    registry.model = make_attrib_model(resX=int)
    thing = ThingModel(name="a")
    assert type(thing.attrib) is registry.model
    assert thing.attrib.resX is None


def test_serialization_options(thing_model):
    ThingModel, _ = thing_model
    thing = ThingModel(name="a", attrib={"fps": 25})

    assert thing.model_dump() == {"name": "a", "attrib": {"fps": 25.0}}
    assert thing.model_dump(exclude_unset=True) == {
        "name": "a",
        "attrib": {"fps": 25.0},
    }
    assert thing.model_dump(include={"attrib": {"fps"}}) == {"attrib": {"fps": 25.0}}
    empty = ThingModel(name="a")
    assert empty.model_dump(exclude_none=True) == {"name": "a", "attrib": {}}
    assert empty.model_dump_json(exclude_unset=True) == '{"name":"a"}'
    assert ThingModel.model_validate_json(thing.model_dump_json()) == thing


def test_json_schema_uses_reference(registry, thing_model):
    ThingModel, _ = thing_model
    registry.model = make_attrib_model(fps=float, resX=int)

    schema = ThingModel.model_json_schema()
    assert schema["properties"]["attrib"]["$ref"] == "#/$defs/ThingAttribModel"
    assert schema["properties"]["attrib"]["title"] == "Thing attributes"
    assert set(schema["$defs"]["ThingAttribModel"]["properties"]) == {"fps", "resX"}


def test_fastapi_route(registry, thing_model):
    ThingModel, _ = thing_model

    app = FastAPI()

    @app.post("/thing")
    def post_thing(thing: ThingModel) -> ThingModel:  # type: ignore[valid-type]
        return thing

    client = TestClient(app)

    # The route validator is compiled here and never rebuilt
    res = client.post("/thing", json={"name": "a", "attrib": {"resX": 1}})
    assert res.status_code == 200
    assert res.json()["attrib"] == {"fps": None}

    registry.model = make_attrib_model(fps=float, resX=int)

    res = client.post("/thing", json={"name": "a", "attrib": {"resX": "1"}})
    assert res.status_code == 200
    assert res.json()["attrib"] == {"fps": None, "resX": 1}

    res = client.post("/thing", json={"name": "a", "attrib": {"resX": "x"}})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "attrib", "resX"]

    schemas = app.openapi()["components"]["schemas"]
    assert "resX" in schemas["ThingAttribModel"]["properties"]
    # The placeholder annotation must not leak to the OpenAPI schema
    assert "BaseModel" not in schemas


def test_copy_returns_the_same_marker(thing_model):
    _, attrib_type = thing_model
    field = {"name": "attrib", "submodel": attrib_type}
    assert copy.deepcopy(field)["submodel"] is attrib_type
    assert copy.copy(attrib_type) is attrib_type


def test_annotation_helpers(registry, thing_model):
    ThingModel, attrib_type = thing_model
    field = ThingModel.model_fields["attrib"]

    assert get_dynamic_model(field) is attrib_type
    assert get_dynamic_model(attrib_type.annotation) is attrib_type
    assert get_dynamic_model(ThingModel.model_fields["name"]) is None
    assert get_dynamic_model(int) is None

    registry.model = make_attrib_model(resX=int)
    assert get_field_annotation(field) is registry.model
    assert get_field_annotation(ThingModel.model_fields["name"]) is str
    assert strip_optional(attrib_type.annotation) is registry.model
    types: list[Any] = list(iter_annotation_types(list[attrib_type.annotation]))  # type: ignore[name-defined]
    assert registry.model in types
