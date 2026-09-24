"""Changing attributes at runtime (without server restart).

The database is not used: `AttributeLibrary._fetch` is replaced
to return the attribute rows the tests need.
"""

import asyncio
import copy
import dataclasses
import json
import os
import sys
from datetime import datetime
from typing import Any

import pytest
import strawberry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from strawberry.scalars import JSON

from ayon_server.entities import FolderEntity, ProjectEntity, UserEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.entities.core.patch import apply_patch
from ayon_server.entities.models import ModelSet
from ayon_server.entities.models.generator import generate_model
from ayon_server.events.default_hooks import DEFAULT_HOOKS, reload_attributes
from ayon_server.graphql import router as graphql_router
from ayon_server.graphql.legacy_attrib import (
    LegacyAttribSelection,
    rewrite_legacy_attrib_selections,
)
from ayon_server.graphql.nodes.common import (
    AttribNamesArgument,
    LegacyAttribSelectionArgument,
)
from ayon_server.graphql.utils import attrib_to_json
from ayon_server.models.attrib_values import AttribDict
from ayon_server.settings.anatomy import Anatomy, get_project_attrib_model

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "api"))


def attribute(name: str, scope: list[str], position: int, **data: Any):
    return {
        "name": name,
        "scope": scope,
        "position": position,
        "builtin": False,
        "data": {"title": name, **data},
    }


BASE_ATTRIBUTES = [
    attribute("fps", ["project", "folder"], 1, type="float", default=25.0),
    attribute("resolutionWidth", ["project", "folder"], 2, type="integer"),
    attribute("description", ["project", "folder"], 3, type="string", inherit=False),
    attribute("startDate", ["project", "folder"], 4, type="datetime"),
    attribute("email", ["user"], 5, type="string"),
]

LIVE_ATTRIBUTE = attribute(
    "liveTest",
    ["project", "folder"],
    10,
    type="integer",
    default=7,
    enum=[{"value": 1, "label": "One"}, {"value": 7, "label": "Seven"}],
)


def load_attributes(rows: list[dict[str, Any]]) -> bool:
    """Simulate attribute rows in the database and reload them"""

    async def fetch() -> list[dict[str, Any]]:
        return copy.deepcopy(rows)

    attribute_library._fetch = fetch  # type: ignore[method-assign]
    return asyncio.run(attribute_library.reload())


@pytest.fixture(autouse=True)
def base_attributes():
    load_attributes(BASE_ATTRIBUTES)
    yield
    load_attributes(BASE_ATTRIBUTES)


def with_live_attribute() -> list[dict[str, Any]]:
    """Base attributes + liveTest - resolutionWidth, fps with a new title"""
    rows = copy.deepcopy(
        [row for row in BASE_ATTRIBUTES if row["name"] != "resolutionWidth"]
    )
    rows[0]["data"]["title"] = "Frames per second"
    return [*rows, LIVE_ATTRIBUTE]


#
# Attribute library
#


def test_reload_is_noop_when_unchanged():
    revision = attribute_library.revision
    assert not load_attributes(BASE_ATTRIBUTES)
    assert attribute_library.revision == revision

    assert load_attributes(with_live_attribute())
    assert attribute_library.revision == revision + 1


def test_reload_replaces_data_at_once():
    old_data = attribute_library.data
    old_folder_names = [a["name"] for a in attribute_library["folder"]]

    load_attributes(with_live_attribute())

    assert attribute_library.data is not old_data
    assert [a["name"] for a in old_data["folder"]] == old_folder_names


def test_lookups_follow_reload():
    assert not attribute_library.is_valid("folder", "liveTest")
    load_attributes(with_live_attribute())
    assert attribute_library.is_valid("folder", "liveTest")
    assert not attribute_library.is_valid("folder", "resolutionWidth")
    assert attribute_library.by_name("liveTest")["type"] == "integer"
    assert attribute_library.project_defaults == {"fps": 25.0, "liveTest": 7}
    assert "default" not in attribute_library.by_name_scoped("folder", "liveTest")


def test_reload_callbacks():
    calls: list[str] = []

    def failing_callback() -> None:
        raise RuntimeError("This must not break the reload")

    async def async_callback() -> None:
        calls.append("async")

    callbacks = attribute_library._reload_callbacks
    attribute_library._reload_callbacks = [failing_callback, async_callback]
    try:
        load_attributes(with_live_attribute())
        load_attributes(with_live_attribute())  # no change, no callbacks
        assert calls == ["async"]
    finally:
        attribute_library._reload_callbacks = callbacks


def test_reload_hook_is_installed_on_all_nodes():
    assert ("server.attributes_updated", reload_attributes, True) in DEFAULT_HOOKS


#
# Entity models
#


def test_entity_attrib_is_a_dict():
    folder = FolderEntity.model.main_model(
        name="a", folder_type="Asset", attrib={"fps": "24", "unknown": 1}
    )
    assert isinstance(folder.attrib, AttribDict)
    assert folder.attrib == {
        "fps": 24.0,
        "resolutionWidth": None,
        "description": None,
        "startDate": None,
    }
    assert folder.attrib.fps == 24.0  # backwards compatible attribute access
    assert folder.model_dump(exclude_unset=True)["attrib"] == {"fps": 24.0}
    assert folder.model_dump(exclude_none=True)["attrib"] == {"fps": 24.0}
    assert json.loads(folder.model_dump_json())["attrib"]["fps"] == 24.0

    patch = FolderEntity.model.patch_model(attrib={"fps": None, "resolutionWidth": "2"})
    assert patch.model_dump(exclude_unset=True) == {
        "attrib": {"fps": None, "resolutionWidth": 2}
    }

    # Patch keeps None values (reverted to inherited values by the entity)
    patched = apply_patch(folder, patch)
    assert patched.attrib == {
        "fps": None,
        "resolutionWidth": 2,
        "description": None,
        "startDate": None,
    }
    assert folder.attrib.fps == 24.0  # original is not modified

    project = ProjectEntity.model.post_model(name="p", code="p")
    assert project.attrib.fps == 25.0  # project defaults

    user = UserEntity.model.main_model(name="user1", attrib={"email": "a@b.c"})
    assert user.attrib.email == "a@b.c"


def test_entity_models_follow_reload():
    main_model = FolderEntity.model.main_model
    post_model = FolderEntity.model.post_model
    patch_model = FolderEntity.model.patch_model

    load_attributes(with_live_attribute())

    assert FolderEntity.model.main_model is main_model
    assert FolderEntity.model.post_model is post_model
    assert FolderEntity.model.patch_model is patch_model

    folder = post_model(name="a", folder_type="Asset", attrib={"liveTest": "3"})
    assert folder.attrib.liveTest == 3
    assert "resolutionWidth" not in folder.attrib
    with pytest.raises(ValidationError) as exc:
        post_model(name="a", folder_type="Asset", attrib={"liveTest": "x"})
    assert exc.value.errors()[0]["loc"] == ("attrib", "liveTest")
    assert patch_model(attrib={"liveTest": 3}).attrib == {"liveTest": 3}
    assert ProjectEntity.model.post_model(name="p", code="p").attrib.liveTest == 7


def test_entity_model_subclass_and_route_follow_reload():
    class CustomFolderModel(FolderEntity.model.patch_model):  # type: ignore
        pass

    app = FastAPI()

    @app.post("/folders")
    def create(folder: FolderEntity.model.post_model) -> dict[str, Any]:  # type: ignore
        return folder.model_dump(exclude_unset=True)  # type: ignore

    client = TestClient(app)
    payload = {"name": "a", "folderType": "Asset", "attrib": {"liveTest": "5"}}
    assert client.post("/folders", json=payload).json()["attrib"] == {}

    load_attributes(with_live_attribute())

    assert CustomFolderModel(attrib={"liveTest": "1"}).attrib.liveTest == 1
    assert client.post("/folders", json=payload).json()["attrib"] == {"liveTest": 5}
    payload["attrib"] = {"liveTest": "x"}
    res = client.post("/folders", json=payload)
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "attrib", "liveTest"]

    attrib_schema = app.openapi()["components"]["schemas"]["FolderAttribModel"]
    assert "liveTest" in attrib_schema["properties"]
    assert attrib_schema["properties"]["fps"]["title"] == "Frames per second"


def test_static_model_set_attributes():
    model_set = ModelSet("folder", [{"name": "static", "type": "integer"}])
    attrib_model = model_set.attrib_model
    load_attributes(with_live_attribute())
    assert model_set.attrib_model is attrib_model


@pytest.mark.parametrize("name", ["model_dump", "model_config"])
def test_attribute_with_reserved_name_is_skipped(name):
    model = generate_model(
        "TestAttribModel",
        [{"name": name, "type": "integer"}, {"name": "valid", "type": "integer"}],
    )
    assert set(model.model_fields) == {"valid"}


#
# Anatomy
#


def test_anatomy_follows_reload():
    assert "liveTest" not in Anatomy.schema()["definitions"]["ProjectAttribModel"][
        "properties"
    ]
    settings_model = get_project_attrib_model()

    load_attributes(with_live_attribute())

    assert get_project_attrib_model() is not settings_model
    properties = Anatomy.schema()["definitions"]["ProjectAttribModel"]["properties"]
    assert "liveTest" in properties
    assert "resolutionWidth" not in properties
    assert Anatomy().attributes.liveTest == 7
    assert Anatomy(attributes={"liveTest": "1"}).attributes.liveTest == 1
    assert Anatomy().model_dump()["attributes"]["liveTest"] == 7


#
# GraphQL
#


def test_graphql_schema_does_not_depend_on_attributes():
    schema = graphql_router.schema
    sdl = str(schema)
    load_attributes(with_live_attribute())
    assert graphql_router.schema is schema
    assert str(graphql_router.schema) == sdl
    assert "AttribType" not in sdl


def test_attrib_to_json():
    data = {"fps": 24, "resolutionWidth": 1920.0, "startDate": "2024-01-01T00:00:00Z"}
    assert attrib_to_json("folder", data) == {
        "fps": 24.0,
        "resolutionWidth": 1920,
        "startDate": "2024-01-01T00:00:00+00:00",
    }
    assert attrib_to_json("folder", data, names=["fps", "description"]) == {
        "fps": 24.0,
        "description": None,
    }
    assert attrib_to_json(
        "project",
        {},
        legacy_selection=["__typename", "rate:fps", "unknown"],
    ) == {"__typename": "ProjectAttribType", "rate": 25.0, "unknown": None}


@pytest.mark.parametrize(
    "query,expected",
    [
        (
            "{ a { attrib { fps\n resolutionWidth } } }",
            '{ a { attrib(legacySelection: ["fps", "resolutionWidth"]) } }',
        ),
        (
            "{ a { attrib{__typename, rate : fps} allAttrib ownAttrib } }",
            '{ a { attrib(legacySelection: ["__typename", "rate:fps"]) '
            "allAttrib ownAttrib } }",
        ),
        ("{ a { attrib allAttrib } }", "{ a { attrib allAttrib } }"),
        ('{ a { attrib(names: ["fps"]) } }', '{ a { attrib(names: ["fps"]) } }'),
        # Not supported: left as they are
        ("{ a { attrib { ...F } } }", "{ a { attrib { ...F } } }"),
        ("{ a { attrib { fps @skip(if: true) } } }", None),
    ],
)
def test_rewrite_legacy_attrib_selections(query, expected):
    result, count = rewrite_legacy_attrib_selections(query)
    assert result == (query if expected is None else expected)
    assert count == (0 if result == query else 1)


# Nodes returning the same data using the former typed attribute field
# and the new JSON field with the compatibility layer

DATA = [
    {"fps": 25, "resolutionWidth": 1920.0, "startDate": "2024-01-01T10:00:00+00:00"},
    {"fps": 24.0, "description": "hello"},
]

TypedAttrib = strawberry.type(
    dataclasses.make_dataclass(
        "FolderAttribType",
        [
            ("fps", float | None, dataclasses.field(default=None)),
            ("resolutionWidth", int | None, dataclasses.field(default=None)),
            ("description", str | None, dataclasses.field(default=None)),
            ("startDate", datetime | None, dataclasses.field(default=None)),
        ],
    )
)


@strawberry.type
class TypedFolder:
    name: str
    _attrib: strawberry.Private[dict[str, Any]]

    @strawberry.field
    def attrib(self) -> TypedAttrib:  # type: ignore[valid-type]
        data = dict(self._attrib)
        if isinstance(data.get("startDate"), str):
            data["startDate"] = datetime.fromisoformat(data["startDate"])
        return TypedAttrib(**data)


@strawberry.type
class TypedQuery:
    @strawberry.field
    def folders(self) -> list[TypedFolder]:
        return [TypedFolder(name=f"f{i}", _attrib=d) for i, d in enumerate(DATA)]


@strawberry.type
class JsonFolder:
    name: str
    _attrib: strawberry.Private[dict[str, Any]]

    @strawberry.field
    def attrib(
        self,
        names: AttribNamesArgument = None,
        legacy_selection: LegacyAttribSelectionArgument = None,
    ) -> JSON:
        return JSON(attrib_to_json("folder", self._attrib, names, legacy_selection))


@strawberry.type
class JsonQuery:
    @strawberry.field
    def folders(self) -> list[JsonFolder]:
        return [JsonFolder(name=f"f{i}", _attrib=d) for i, d in enumerate(DATA)]


@pytest.mark.parametrize(
    "query",
    [
        "query FoldersQuery {\n  folders {\n    name\n    attrib {\n"
        "      resolutionWidth\n      fps\n      startDate\n    }\n  }\n}",
        "{ folders { attrib { fps description } name } }",
        "{ folders { attrib { __typename rate: fps } } }",
        "{ folders { a: attrib { fps } b: attrib { resolutionWidth } } }",
    ],
)
def test_legacy_queries_return_the_same_result(query):
    typed = strawberry.Schema(query=TypedQuery)
    new = strawberry.Schema(query=JsonQuery, extensions=[LegacyAttribSelection])

    expected = typed.execute_sync(query)
    result = new.execute_sync(query)
    assert not expected.errors
    assert not result.errors
    assert json.dumps(result.data) == json.dumps(expected.data)
