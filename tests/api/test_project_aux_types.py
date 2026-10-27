"""Folder types, task types, statuses and tags of a project.

They are stored in the project tables and exposed by the project REST
endpoints (camelCase), the project anatomy (snake_case, settings models)
and GraphQL. Entities refer to them by name, so renaming a type must update
the entities using it (`original_name`).
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from .conftest import TempProject, create_temp_project

AUX_TYPES = ("folderTypes", "taskTypes", "statuses", "tags")


@pytest.fixture
def project(api: httpx.Client) -> Iterator[TempProject]:
    with create_temp_project(api) as project:
        yield project


def get(project: TempProject) -> dict[str, Any]:
    return project.api.get(f"/api/projects/{project.name}").json()


def patch(project: TempProject, data: dict[str, Any]) -> httpx.Response:
    return project.api.patch(f"/api/projects/{project.name}", json=data)


def get_anatomy(project: TempProject) -> dict[str, Any]:
    return project.api.get(f"/api/projects/{project.name}/anatomy").json()


def post_anatomy(project: TempProject, anatomy: dict[str, Any]) -> httpx.Response:
    return project.api.post(f"/api/projects/{project.name}/anatomy", json=anatomy)


def entities(project: TempProject) -> dict[str, str]:
    """Create a folder and a task using the first types and status."""
    folder_id = project.create(
        "folder",
        name="shot",
        folderType=project.folder_types[0],
        status=project.statuses[0],
        tags=["important"],
    )
    task_id = project.create(
        "task", name="comp", taskType=project.task_types[0], folderId=folder_id
    )
    return {"folder": folder_id, "task": task_id}


#
# Shape
#


def test_rest_shape(project: TempProject):
    data = get(project)
    assert set(data["folderTypes"][0]) <= {"name", "shortName", "color", "icon"}
    assert set(data["taskTypes"][0]) <= {"name", "shortName", "color", "icon"}
    assert set(data["statuses"][0]) <= {
        "name",
        "shortName",
        "state",
        "icon",
        "color",
        "scope",
    }
    assert set(data["tags"][0]) <= {"name", "color"}
    assert set(data["linkTypes"][0]) == {
        "name",
        "linkType",
        "inputType",
        "outputType",
        "data",
    }


def test_anatomy_shape(project: TempProject):
    anatomy = get_anatomy(project)
    folder_type = anatomy["folder_types"][0]
    # the original name is used to rename the types
    assert folder_type["original_name"] == folder_type["name"]
    assert "shortName" in folder_type
    assert anatomy["statuses"][0]["original_name"] == anatomy["statuses"][0]["name"]


def test_graphql_matches_rest(project: TempProject, graphql):
    data = get(project)
    result = graphql(
        f'{{ project(name: "{project.name}") {{ '
        "folderTypes { name shortName color icon } "
        "taskTypes { name shortName color icon } "
        "statuses { name shortName state icon color scope } "
        "tags { name color } } }"
    )["project"]
    for key in AUX_TYPES:
        rest = data[key]
        assert len(result[key]) == len(rest), key
        for gql_item, rest_item in zip(result[key], rest, strict=True):
            for k, v in rest_item.items():
                assert gql_item[k] == v, (key, k)


#
# REST (project PATCH)
#


def test_add_type(project: TempProject):
    folder_types = get(project)["folderTypes"]
    response = patch(project, {"folderTypes": [*folder_types, {"name": "NewType"}]})
    assert response.status_code == 204, response.text
    new = get(project)["folderTypes"][-1]
    # stored as provided (default values are not added)
    assert new == {"name": "NewType"}
    project.create("folder", name="new", folderType="NewType")


def test_reorder(project: TempProject):
    statuses = get(project)["statuses"]
    assert patch(project, {"statuses": statuses[::-1]}).status_code == 204
    assert get(project)["statuses"] == statuses[::-1]


def test_update_values(project: TempProject):
    task_types = get(project)["taskTypes"]
    task_types[0] = {**task_types[0], "color": "#123456", "shortName": "x"}
    assert patch(project, {"taskTypes": task_types}).status_code == 204
    updated = get(project)["taskTypes"][0]
    assert updated["color"] == "#123456"
    assert updated["shortName"] == "x"


@pytest.mark.parametrize(
    "key,entity_type,field",
    [
        ("folderTypes", "folder", "folderType"),
        ("taskTypes", "task", "taskType"),
        ("statuses", "folder", "status"),
    ],
)
def test_rename_updates_entities(
    project: TempProject, key: str, entity_type: str, field: str
):
    ids = entities(project)
    types = get(project)[key]
    old = types[0]["name"]
    types[0] = {**types[0], "name": f"{old}Renamed", "original_name": old}
    response = patch(project, {key: types})
    assert response.status_code == 204, response.text
    assert [t["name"] for t in get(project)[key]][0] == f"{old}Renamed"
    assert project.get(entity_type, ids[entity_type])[field] == f"{old}Renamed"


@pytest.mark.xfail(
    strict=True,
    reason="camelCase originalName is ignored: the renamed type is added "
    "and the original one deleted, which fails while it is used",
)
def test_rename_with_camelcase_original_name(project: TempProject):
    ids = entities(project)
    types = get(project)["folderTypes"]
    old = types[0]["name"]
    types[0] = {**types[0], "name": f"{old}Renamed", "originalName": old}
    assert patch(project, {"folderTypes": types}).status_code == 204
    assert project.get("folder", ids["folder"])["folderType"] == f"{old}Renamed"


def test_remove_used_type(project: TempProject):
    entities(project)
    types = get(project)["folderTypes"]
    response = patch(project, {"folderTypes": types[1:]})
    assert response.status_code == 409
    assert get(project)["folderTypes"] == types


def test_remove_unused_type(project: TempProject):
    types = get(project)["folderTypes"]
    assert patch(project, {"folderTypes": types[:-1]}).status_code == 204
    assert get(project)["folderTypes"] == types[:-1]


def test_rename_tag(project: TempProject):
    ids = entities(project)
    tags = get(project)["tags"]
    tags[0] = {**tags[0], "name": "renamed", "original_name": tags[0]["name"]}
    assert patch(project, {"tags": tags}).status_code == 204
    assert get(project)["tags"][0]["name"] == "renamed"
    # tags of the entities are not references (they keep the old name)
    assert project.get("folder", ids["folder"])["tags"] == ["important"]


#
# Anatomy
#


def test_anatomy_round_trip_changes_nothing(project: TempProject):
    entities(project)
    before = get(project)
    assert post_anatomy(project, get_anatomy(project)).status_code == 204
    after = get(project)
    for key in (*AUX_TYPES, "linkTypes", "attrib"):
        assert after[key] == before[key], key


def test_rename_via_anatomy(project: TempProject):
    ids = entities(project)
    anatomy = get_anatomy(project)
    old = anatomy["folder_types"][0]["name"]
    anatomy["folder_types"][0]["name"] = f"{old}Renamed"  # original_name is kept
    assert post_anatomy(project, anatomy).status_code == 204
    assert project.get("folder", ids["folder"])["folderType"] == f"{old}Renamed"


def test_anatomy_adds_default_values(project: TempProject):
    folder_types = get(project)["folderTypes"]
    patch(project, {"folderTypes": [*folder_types, {"name": "NewType"}]})
    # the anatomy (settings models) shows the default values ...
    new = get_anatomy(project)["folder_types"][-1]
    assert new["name"] == "NewType"
    assert new["color"] and new["icon"]
    # ... and stores them when it is saved
    assert post_anatomy(project, get_anatomy(project)).status_code == 204
    assert get(project)["folderTypes"][-1]["color"] == new["color"]


def test_deploy_custom_anatomy(api: httpx.Client, project: TempProject):
    anatomy = get_anatomy(project)
    anatomy["folder_types"] = [{"name": "Custom", "icon": "star"}]
    name = f"{project.name}b"
    response = api.post(
        "/api/projects", json={"name": name, "code": "cust", "anatomy": anatomy}
    )
    assert response.status_code == 201, response.text
    try:
        folder_types = api.get(f"/api/projects/{name}").json()["folderTypes"]
        assert [t["name"] for t in folder_types] == ["Custom"]
        assert folder_types[0]["icon"] == "star"
    finally:
        api.delete(f"/api/projects/{name}")
