"""Attribute values of the entity models (default attributes, see conftest.py)"""

import copy
import pickle
from typing import Annotated, ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ayon_server.entities.models.common import ATTRIB, EntityModel
from ayon_server.entities.models.generator import generate_model
from ayon_server.models.attrib_values import STORED_VALUES_CONTEXT, AttribDict
from ayon_server.types import Field


class ThingModel(EntityModel):
    entity_type: ClassVar[str] = "folder"

    name: str
    attrib: Annotated[AttribDict, ATTRIB] = Field(default_factory=AttribDict)


#
# AttribDict
#


def test_attribute_access():
    attrib = AttribDict({"fps": 25})
    assert attrib.fps == 25
    assert attrib.missing is None
    attrib.resolutionWidth = 1920
    assert attrib["resolutionWidth"] == 1920
    del attrib.fps
    assert attrib == {"resolutionWidth": 1920}
    with pytest.raises(AttributeError):
        attrib.__foo__  # noqa: B018


def test_model_dump():
    attrib = AttribDict({"fps": 25, "resolutionWidth": None})
    assert attrib.model_dump() == {"fps": 25, "resolutionWidth": None}
    assert attrib.model_dump(exclude_none=True) == {"fps": 25}
    assert attrib.model_dump(exclude_unset=True) == attrib.model_dump()
    assert attrib.dict() == attrib.model_dump()


@pytest.mark.parametrize(
    "func",
    [
        copy.copy,
        copy.deepcopy,
        lambda a: a.copy(),
        lambda a: pickle.loads(pickle.dumps(a)),
    ],
)
def test_copies_are_attrib_dicts(func):
    attrib = AttribDict({"fps": 25})
    copied = func(attrib)
    assert isinstance(copied, AttribDict)
    assert copied == attrib


#
# Validation (entity models)
#


def test_only_given_attributes_are_kept():
    thing = ThingModel(name="a", attrib={"fps": "25", "unknown": 1})
    assert isinstance(thing.attrib, AttribDict)
    assert thing.attrib == {"fps": 25.0}  # converted, undefined attributes dropped
    assert ThingModel(name="a").attrib == {}
    assert ThingModel(name="a", attrib={"fps": None}).attrib == {"fps": None}


def test_invalid_values_are_rejected():
    with pytest.raises(ValidationError) as exc:
        ThingModel(name="a", attrib={"resolutionWidth": "nope"})
    assert exc.value.errors()[0]["loc"] == ("attrib", "resolutionWidth")


def test_stored_values_are_not_validated():
    thing = ThingModel.model_validate(
        {"name": "a", "attrib": {"resolutionWidth": 0}},
        context=STORED_VALUES_CONTEXT,
    )
    assert thing.attrib == {"resolutionWidth": 0}


def test_validate_does_not_modify_the_source_model():
    source_model = generate_model(
        "Source",
        [
            {"name": "fps", "type": "float", "title": "FPS"},
            {"name": "removed", "type": "string", "title": "Removed"},
        ],
    )
    source = source_model(fps=25, removed="x")
    assert ThingModel(name="a", attrib=source).attrib == {"fps": 25.0}
    assert source.model_fields_set == {"fps", "removed"}


def test_serialization():
    thing = ThingModel(name="a", attrib={"fps": 25})
    assert thing.model_dump() == {"name": "a", "attrib": {"fps": 25.0}}
    assert thing.model_dump(include={"attrib": {"fps"}}) == {"attrib": {"fps": 25.0}}
    # exclude_none applies to the attributes (unset attributes are not stored)
    unset = ThingModel(name="a", attrib={"fps": 25, "description": None})
    assert unset.model_dump(exclude_none=True)["attrib"] == {"fps": 25.0}
    assert unset.model_dump()["attrib"] == {"fps": 25.0, "description": None}
    assert ThingModel.model_validate_json(thing.model_dump_json()) == thing


def test_json_schema_is_a_plain_object():
    # Attributes are configured at runtime, schemas describe a plain object
    attrib_schema = ThingModel.model_json_schema()["properties"]["attrib"]
    assert attrib_schema["type"] == "object"
    assert attrib_schema["additionalProperties"] is True


def test_fastapi_route():
    app = FastAPI()

    @app.post("/thing")
    def post_thing(thing: ThingModel) -> ThingModel:
        return thing

    client = TestClient(app)
    res = client.post("/thing", json={"name": "a", "attrib": {"fps": "24"}})
    assert res.json()["attrib"] == {"fps": 24.0}
    res = client.post("/thing", json={"name": "a", "attrib": {"fps": "x"}})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "attrib", "fps"]
