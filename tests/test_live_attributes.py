"""Changing attributes at runtime (without server restart).

The database is not used: `AttributeLibrary._fetch` is replaced
to return the attribute rows the tests need.
"""

import asyncio
import copy
import os
import sys
from typing import Any

import pytest
import strawberry
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ayon_server.entities import FolderEntity, ProjectEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.entities.models import ModelSet
from ayon_server.entities.models.generator import generate_model
from ayon_server.events.default_hooks import DEFAULT_HOOKS, reload_attributes
from ayon_server.graphql import router as graphql_router
from ayon_server.graphql.nodes.folder import FolderAttribType
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
]

LIVE_ATTRIBUTE = attribute(
    "liveTest",
    ["project", "folder"],
    4,
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
    old_folder = attribute_library["folder"]
    old_folder_names = [a["name"] for a in old_folder]

    load_attributes(with_live_attribute())

    # Previous data is replaced, not modified, so readers holding it
    # never see a partially updated list
    assert attribute_library.data is not old_data
    assert [a["name"] for a in old_folder] == old_folder_names
    assert [a["name"] for a in attribute_library["folder"]] == [
        "fps",
        "description",
        "liveTest",
    ]


def test_lookups_follow_reload():
    assert attribute_library.is_valid("folder", "resolutionWidth")
    assert not attribute_library.is_valid("folder", "liveTest")
    with pytest.raises(KeyError):
        attribute_library.by_name("liveTest")

    load_attributes(with_live_attribute())

    assert attribute_library.is_valid("folder", "liveTest")
    assert not attribute_library.is_valid("folder", "resolutionWidth")
    assert not attribute_library.is_valid("user", "liveTest")
    assert attribute_library.by_name("liveTest")["type"] == "integer"
    assert attribute_library.by_name_scoped("folder", "liveTest")["name"] == "liveTest"
    with pytest.raises(KeyError):
        attribute_library.by_name_scoped("user", "liveTest")
    assert set(attribute_library.inheritable_attributes()) == {"fps", "liveTest"}
    assert attribute_library.project_defaults == {"fps": 25.0, "liveTest": 7}
    # Only project attributes have defaults
    assert "default" not in attribute_library.by_name_scoped("folder", "liveTest")
    assert [row["name"] for row in attribute_library.info_data] == [
        "fps",
        "description",
        "liveTest",
    ]


def test_reload_callbacks():
    calls: list[str] = []

    def sync_callback() -> None:
        calls.append("sync")

    def failing_callback() -> None:
        raise RuntimeError("This must not break the reload")

    async def async_callback() -> None:
        calls.append("async")

    callbacks = attribute_library._reload_callbacks
    attribute_library._reload_callbacks = [
        sync_callback,
        failing_callback,
        async_callback,
    ]
    try:
        load_attributes(with_live_attribute())
        assert calls == ["sync", "async"]
        # no change, no callbacks
        load_attributes(with_live_attribute())
        assert calls == ["sync", "async"]
    finally:
        attribute_library._reload_callbacks = callbacks


def test_reload_hook_is_installed_on_all_nodes():
    assert ("server.attributes_updated", reload_attributes, True) in DEFAULT_HOOKS


#
# Entity models
#


def test_entity_models_follow_reload():
    main_model = FolderEntity.model.main_model
    post_model = FolderEntity.model.post_model
    patch_model = FolderEntity.model.patch_model
    attrib_model = FolderEntity.model.attrib_model
    assert FolderEntity.model.attrib_model is attrib_model  # cached

    load_attributes(with_live_attribute())

    # Only the attribute model is regenerated
    assert FolderEntity.model.main_model is main_model
    assert FolderEntity.model.post_model is post_model
    assert FolderEntity.model.patch_model is patch_model
    assert FolderEntity.model.attrib_model is not attrib_model
    assert set(FolderEntity.model.attrib_model.model_fields) == {
        "fps",
        "description",
        "liveTest",
    }

    folder = post_model(name="a", folder_type="Asset", attrib={"liveTest": "3"})
    assert folder.attrib.liveTest == 3
    with pytest.raises(ValidationError) as exc:
        post_model(name="a", folder_type="Asset", attrib={"liveTest": "x"})
    assert exc.value.errors()[0]["loc"] == ("attrib", "liveTest")

    patch = patch_model(attrib={"liveTest": 3})
    assert patch.model_dump(exclude_unset=True) == {"attrib": {"liveTest": 3}}

    # Removed attributes are ignored
    folder = main_model(name="a", folder_type="Asset", attrib={"resolutionWidth": 1})
    assert "resolutionWidth" not in folder.attrib.model_dump()

    # Project attribute defaults
    project = ProjectEntity.model.post_model(name="p", code="p")
    assert project.attrib.liveTest == 7


def test_entity_model_subclass_follows_reload():
    class CustomFolderModel(FolderEntity.model.patch_model):  # type: ignore
        pass

    load_attributes(with_live_attribute())
    assert CustomFolderModel(attrib={"liveTest": "1"}).attrib.liveTest == 1


def test_entity_route_follows_reload():
    app = FastAPI()

    @app.post("/folders")
    def create(folder: FolderEntity.model.post_model) -> dict[str, Any]:  # type: ignore
        return folder.model_dump(exclude_unset=True)  # type: ignore

    client = TestClient(app)
    payload = {"name": "a", "folderType": "Asset", "attrib": {"liveTest": "5"}}
    assert client.post("/folders", json=payload).json()["attrib"] == {}

    load_attributes(with_live_attribute())

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
    assert set(attrib_model.model_fields) == {"static"}


@pytest.mark.parametrize("name", ["model_dump", "model_config"])
def test_attribute_with_reserved_name_is_skipped(name):
    # Must not crash (the model generator exits the process when
    # the final model cannot be created)
    model = generate_model(
        "TestAttribModel",
        [{"name": name, "type": "integer"}, {"name": "valid", "type": "integer"}],
    )
    assert set(model.model_fields) == {"valid"}


#
# Anatomy
#


def test_anatomy_follows_reload():
    schema = Anatomy.schema()
    assert "liveTest" not in schema["definitions"]["ProjectAttribModel"]["properties"]
    settings_model = get_project_attrib_model()
    assert get_project_attrib_model() is settings_model  # cached

    load_attributes(with_live_attribute())

    assert get_project_attrib_model() is not settings_model
    schema = Anatomy.schema()
    properties = schema["definitions"]["ProjectAttribModel"]["properties"]
    assert "liveTest" in properties
    assert "resolutionWidth" not in properties
    assert Anatomy().attributes.liveTest == 7
    assert Anatomy(attributes={"liveTest": "1"}).attributes.liveTest == 1

    # Backwards compatible module attribute
    from ayon_server.settings import anatomy

    assert anatomy.ProjectAttribModel is get_project_attrib_model()


#
# GraphQL
#


async def graphql_type_fields(type_name: str) -> set[str]:
    res = await graphql_router.schema.execute(
        '{ __type(name: "%s") { fields { name } } }' % type_name,
        context_value={},
    )
    assert not res.errors
    assert res.data
    return {field["name"] for field in res.data["__type"]["fields"]}


def test_graphql_schema_follows_reload():
    schema = graphql_router.schema
    fields = asyncio.run(graphql_type_fields("FolderAttribType"))
    assert "resolutionWidth" in fields
    assert "liveTest" not in fields

    load_attributes(with_live_attribute())

    assert graphql_router.schema is not schema
    fields = asyncio.run(graphql_type_fields("FolderAttribType"))
    assert "liveTest" in fields
    assert "resolutionWidth" not in fields
    assert "liveTest" in asyncio.run(graphql_type_fields("ProjectAttribType"))

    # Existing attribute type (referenced by node resolvers) resolves new fields
    @strawberry.type
    class Query:
        @strawberry.field
        def attrib(self) -> FolderAttribType:
            return FolderAttribType(liveTest=3, fps=24.0)  # type: ignore[call-arg]

    res = strawberry.Schema(query=Query).execute_sync("{ attrib { liveTest fps } }")
    assert not res.errors
    assert res.data == {"attrib": {"liveTest": 3, "fps": 24.0}}


def test_graphql_entity_type_without_attributes():
    from ayon_server.graphql.nodes.representation import RepresentationAttribType

    # No attribute is enabled for representations in BASE_ATTRIBUTES
    assert asyncio.run(graphql_type_fields("RepresentationAttribType")) == {"empty"}
    assert RepresentationAttribType().empty is None  # type: ignore[attr-defined]

    rows = [*BASE_ATTRIBUTES, attribute("path", ["representation"], 5)]
    load_attributes(rows)
    assert asyncio.run(graphql_type_fields("RepresentationAttribType")) == {"path"}
    rep_attrib = RepresentationAttribType(path="/a")  # type: ignore[call-arg]
    assert rep_attrib.path == "/a"  # type: ignore[attr-defined]

    load_attributes(BASE_ATTRIBUTES)
    assert asyncio.run(graphql_type_fields("RepresentationAttribType")) == {"empty"}


def test_graphql_schema_not_rebuilt_without_changes():
    load_attributes(with_live_attribute())
    schema = graphql_router.schema
    load_attributes(with_live_attribute())
    assert graphql_router.schema is schema


#
# Attributes API
#


def test_attribute_changes_are_applied_and_propagated(monkeypatch):
    from attributes import attributes as attributes_api  # type: ignore

    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(topic: str, **kwargs: Any) -> str:
        # Reload is applied locally before other nodes are notified
        assert attribute_library.is_valid("folder", "liveTest")
        dispatched.append((topic, kwargs))
        return "event-id"

    monkeypatch.setattr(attributes_api.EventStream, "dispatch", dispatch)

    async def fetch() -> list[dict[str, Any]]:
        return with_live_attribute()

    attribute_library._fetch = fetch  # type: ignore[method-assign]
    asyncio.run(attributes_api.apply_attribute_changes("admin"))

    assert [topic for topic, _ in dispatched] == ["server.attributes_updated"]
    assert dispatched[0][1]["user"] == "admin"
    assert FolderEntity.model.post_model(
        name="a", folder_type="Asset", attrib={"liveTest": 1}
    ).attrib.liveTest == 1
