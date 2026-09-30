import copy
import pickle

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from ayon_server.models.attrib_values import AttribDict, AttribValues


def make_attrib_model(**fields: type) -> type[BaseModel]:
    return create_model(  # type: ignore[call-overload,no-any-return]
        "ThingAttribModel",
        __config__=ConfigDict(coerce_numbers_to_str=True),
        **{name: (ftype | None, Field(None)) for name, ftype in fields.items()},
    )


class Registry:
    """Holds the current attribute model, which may be replaced"""

    def __init__(self) -> None:
        self.model = make_attrib_model(fps=float)


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def models(registry: Registry):
    attrib_type = AttribValues(lambda: registry.model)
    attrib_patch_type = AttribValues(lambda: registry.model, partial=True)

    class ThingModel(BaseModel):
        name: str
        attrib: attrib_type.annotation = Field(  # type: ignore[name-defined]
            default_factory=attrib_type,
            title="Thing attributes",
        )

    class ThingPatchModel(BaseModel):
        attrib: attrib_patch_type.annotation = Field(  # type: ignore[name-defined]
            default_factory=attrib_patch_type,
        )

    return ThingModel, ThingPatchModel


#
# AttribDict
#


def test_attrib_dict_attribute_access():
    attrib = AttribDict({"fps": 25})
    assert attrib.fps == 25
    assert attrib.missing is None
    attrib.resolutionWidth = 1920
    assert attrib["resolutionWidth"] == 1920
    assert attrib.model_fields_set == {"fps", "resolutionWidth"}
    del attrib.fps
    assert "fps" not in attrib
    assert attrib.model_fields_set == {"resolutionWidth"}
    with pytest.raises(AttributeError):
        attrib.__foo__  # noqa: B018


def test_attrib_dict_fields_set():
    attrib = AttribDict({"fps": 25, "resolutionWidth": None}, fields_set={"fps"})
    assert attrib.model_dump() == {"fps": 25, "resolutionWidth": None}
    assert attrib.model_dump(exclude_unset=True) == {"fps": 25}
    assert attrib.model_dump(exclude_none=True) == {"fps": 25}
    attrib["resolutionWidth"] = 1
    attrib.update({"frameStart": 1})
    assert attrib.model_fields_set == {"fps", "resolutionWidth", "frameStart"}


@pytest.mark.parametrize(
    "func",
    [
        copy.copy,
        copy.deepcopy,
        lambda a: a.copy(),
        lambda a: pickle.loads(pickle.dumps(a)),
    ],
)
def test_attrib_dict_copy_keeps_fields_set(func):
    attrib = AttribDict({"fps": 25, "resolutionWidth": None}, fields_set={"fps"})
    copied = func(attrib)
    assert isinstance(copied, AttribDict)
    assert copied == attrib
    assert copied.model_fields_set == {"fps"}


#
# AttribValues
#


def test_full_and_partial_validation(models):
    ThingModel, ThingPatchModel = models

    thing = ThingModel(name="a", attrib={"fps": "25", "unknown": 1})
    assert isinstance(thing.attrib, AttribDict)
    # Full: all attributes (as the attribute model did), unknown ignored
    assert thing.attrib == {"fps": 25.0}
    assert ThingModel(name="a").attrib == {"fps": None}

    patch = ThingPatchModel(attrib={})
    assert patch.attrib == {}
    patch = ThingPatchModel(attrib={"fps": None})
    assert patch.attrib == {"fps": None}


def test_validation_follows_model_replacement(registry, models):
    ThingModel, _ = models
    registry.model = make_attrib_model(fps=float, resX=int)

    thing = ThingModel(name="a", attrib={"resX": "2"})
    assert thing.attrib == {"fps": None, "resX": 2}

    with pytest.raises(ValidationError) as exc:
        ThingModel(name="a", attrib={"resX": "nope"})
    assert exc.value.errors()[0]["loc"] == ("attrib", "resX")


def test_serialization(models):
    ThingModel, _ = models
    thing = ThingModel(name="a", attrib={"fps": 25})
    empty = ThingModel(name="a")

    assert thing.model_dump() == {"name": "a", "attrib": {"fps": 25.0}}
    assert empty.model_dump(exclude_none=True) == {"name": "a", "attrib": {}}
    # Unset attributes are excluded the same way as for attribute models
    assert empty.model_dump(exclude_unset=True) == {"name": "a"}
    unset = ThingModel(name="a", attrib={})
    assert unset.model_dump(exclude_unset=True) == {"name": "a", "attrib": {}}
    assert thing.model_dump(include={"attrib": {"fps"}}) == {"attrib": {"fps": 25.0}}
    assert ThingModel.model_validate_json(thing.model_dump_json()) == thing


def test_revalidation_keeps_fields_set(registry, models):
    ThingModel, _ = models
    thing = ThingModel(name="a", attrib={"fps": 25})
    registry.model = make_attrib_model(fps=float, resX=int)
    copied = ThingModel(name="b", attrib=thing.attrib)
    assert copied.attrib == {"fps": 25.0, "resX": None}
    assert copied.attrib.model_fields_set == {"fps"}


def test_json_schema_does_not_depend_on_attributes(registry, models):
    # Attributes are configured at runtime, schemas describe a plain object
    ThingModel, _ = models
    schema = ThingModel.model_json_schema()
    registry.model = make_attrib_model(fps=float, resX=int)
    assert ThingModel.model_json_schema() == schema
    attrib_schema = schema["properties"]["attrib"]
    assert attrib_schema["type"] == "object"
    assert attrib_schema["additionalProperties"] is True


def test_fastapi_route(registry, models):
    ThingModel, _ = models
    app = FastAPI()

    @app.post("/thing")
    def post_thing(thing: ThingModel) -> ThingModel:  # type: ignore[valid-type]
        return thing

    client = TestClient(app)
    res = client.post("/thing", json={"name": "a", "attrib": {"resX": 1}})
    assert res.json()["attrib"] == {"fps": None}

    registry.model = make_attrib_model(fps=float, resX=int)

    res = client.post("/thing", json={"name": "a", "attrib": {"resX": "1"}})
    assert res.json()["attrib"] == {"fps": None, "resX": 1}
    res = client.post("/thing", json={"name": "a", "attrib": {"resX": "x"}})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "attrib", "resX"]


def test_validate_does_not_modify_the_source_model(models):
    ThingModel, _ = models
    source_model = make_attrib_model(fps=float, removed=str)
    source = source_model(fps=25, removed="x")
    ThingModel(name="a", attrib=source)
    assert source.model_fields_set == {"fps", "removed"}
