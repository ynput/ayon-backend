"""Attribute values in REST and GraphQL (untyped attributes)."""

import json
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest

from .conftest import GraphQL

SAMPLE_SIZE = 50


def normalize(value: Any) -> Any:
    """Make values comparable (datetime formats, 25 == 25.0)."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def assert_same_values(rest: dict[str, Any], graphql: dict[str, Any], label: str):
    rest = {k: v for k, v in rest.items() if v is not None}
    graphql = {k: v for k, v in graphql.items() if v is not None}
    for key in rest.keys() | graphql.keys():
        assert normalize(rest.get(key)) == normalize(graphql.get(key)), (
            f"{label}: {key} REST={rest.get(key)!r} GraphQL={graphql.get(key)!r}"
        )


def sample_nodes(graphql: GraphQL, project_name: str, kind: str, fields: str):
    data = graphql(
        f'{{ project(name: "{project_name}") {{ {kind}(first: {SAMPLE_SIZE}) '
        f"{{ edges {{ node {{ id {fields} }} }} }} }} }}"
    )
    return [edge["node"] for edge in data["project"][kind]["edges"]]


def get_attributes(api: httpx.Client) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in api.get("/api/attributes").json()["attributes"]}


#
# REST and GraphQL return the same values
#


@pytest.mark.parametrize("kind", ["folders", "tasks"])
def test_rest_and_graphql_match(api, graphql, project_name, kind):
    nodes = sample_nodes(graphql, project_name, kind, "attrib allAttrib ownAttrib")
    assert nodes
    for node in nodes:
        rest = api.get(f"/api/projects/{project_name}/{kind}/{node['id']}").json()
        label = f"{kind} {node['id']}"
        assert_same_values(rest["attrib"], node["attrib"], f"{label} attrib")
        assert_same_values(rest["attrib"], json.loads(node["allAttrib"]), label)
        assert sorted(rest["ownAttrib"]) == sorted(node["ownAttrib"]), label


def test_rest_and_graphql_match_for_project(api, graphql, project_name):
    rest = api.get(f"/api/projects/{project_name}").json()
    data = graphql(f'{{ project(name: "{project_name}") {{ attrib allAttrib }} }}')
    assert_same_values(rest["attrib"], data["project"]["attrib"], "project attrib")
    assert_same_values(
        rest["attrib"], json.loads(data["project"]["allAttrib"]), "project allAttrib"
    )


@pytest.mark.parametrize("kind", ["folders", "tasks"])
def test_own_attrib_does_not_depend_on_field_order(graphql, project_name, kind):
    own_first = sample_nodes(graphql, project_name, kind, "ownAttrib allAttrib attrib")
    own_last = sample_nodes(graphql, project_name, kind, "allAttrib attrib ownAttrib")
    for a, b in zip(own_first, own_last, strict=True):
        assert sorted(a["ownAttrib"]) == sorted(b["ownAttrib"]), a["id"]


def test_legacy_attrib_selection(graphql, project_name):
    """Former typed `attrib { ... }` selections return the same values"""
    names = ["fps", "resolutionWidth", "frameStart"]
    fields = " ".join(names)
    legacy = sample_nodes(
        graphql,
        project_name,
        "folders",
        f"attrib {{ __typename {fields} rate: fps }}",
    )
    new = sample_nodes(
        graphql, project_name, "folders", f"attrib(names: {json.dumps(names)})"
    )
    for old_node, new_node in zip(legacy, new, strict=True):
        assert old_node["attrib"]["__typename"] == "FolderAttribType"
        assert old_node["attrib"]["rate"] == new_node["attrib"]["fps"]
        for name in names:
            assert old_node["attrib"][name] == new_node["attrib"][name]


#
# Writing attribute values
#


def test_invalid_attribute_value_is_rejected(api, graphql, project_name):
    if get_attributes(api).get("fps", {}).get("data", {}).get("type") != "float":
        pytest.skip("fps attribute is not a float")
    folder_id = sample_nodes(graphql, project_name, "folders", "")[0]["id"]
    url = f"/api/projects/{project_name}/folders/{folder_id}"
    before = api.get(url).json()

    response = api.patch(url, json={"attrib": {"fps": "not a number"}})
    assert response.status_code == 400
    assert api.get(url).json()["attrib"] == before["attrib"]


#
# Attribute definitions
#


@pytest.mark.parametrize(
    "name,data,message",
    [
        ("json", {"type": "string", "title": "Json"}, "reserved"),
        (
            "apitestregex",
            {"type": "string", "title": "Regex", "regex": "^(?!tmp).*$"},
            "not supported",
        ),
        (
            "apitestdefault",
            {"type": "integer", "title": "Default", "gt": 0, "default": 0},
            "Default value",
        ),
    ],
)
def test_invalid_attribute_definition_is_rejected(api, name, data, message):
    payload = {"position": 999, "scope": ["folder"], "data": data}
    response = api.put(f"/api/attributes/{name}", json=payload)
    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert name not in get_attributes(api)


def test_attributes_can_change_at_runtime(api, graphql, project_name):
    """New and deleted attributes are used without a server restart"""
    name = f"apiTest{uuid.uuid4().hex[:8]}"
    payload = {
        "position": 999,
        "scope": ["project", "folder"],
        "data": {"type": "integer", "title": "API test", "default": 7},
    }

    def check(expected: int | None) -> None:
        present = expected is not None
        info = api.get("/api/info").json()
        assert any(a["name"] == name for a in info["attributes"]) is present
        schema = api.get("/api/anatomy/schema").json()
        properties = schema["definitions"]["ProjectAttribModel"]["properties"]
        assert (name in properties) is present
        project = api.get(f"/api/projects/{project_name}").json()
        assert project["attrib"].get(name) == expected
        names = json.dumps([name])
        data = graphql(
            f'{{ project(name: "{project_name}") {{ attrib(names: {names}) '
            "folders(first: 1) { edges { node { "
            f"attrib(names: {names}) }} }} }} }} }}"
        )["project"]
        assert data["attrib"][name] == expected
        folder = data["folders"]["edges"][0]["node"]
        assert folder["attrib"][name] == expected  # inherited from the project

    assert api.put(f"/api/attributes/{name}", json=payload).status_code == 204
    try:
        check(7)
    finally:
        assert api.delete(f"/api/attributes/{name}").status_code == 204
    check(None)


#
# Entity types
#


def test_activity_rejects_project_entity_type(api, project_name):
    operation = {
        "type": "create",
        "data": {
            "entityType": "project",
            "entityId": uuid.uuid4().hex,
            "activityType": "comment",
            "body": "API test",
        },
    }
    response = api.post(
        f"/api/projects/{project_name}/operations/activities",
        json={"operations": [operation]},
    )
    assert response.status_code == 200
    result = response.json()["operations"][0]
    assert not result["success"]
    assert result["status"] == 400
    assert "Invalid entity type" in result["detail"]
