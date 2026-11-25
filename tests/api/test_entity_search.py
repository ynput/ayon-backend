"""`textSearch` in GraphQL, backed by the entity_search index."""

import json
import time
import uuid
from collections.abc import Iterator

import httpx
import pytest

from .conftest import TempProject


def search(client: httpx.Client, project: str, text: str, scope: list[str]) -> list:
    """Return the sorted paths of the folders found by textSearch."""
    query = (
        f'{{ project(name: "{project}") {{ folders(textSearch: {json.dumps(text)}, '
        f"textSearchScope: {json.dumps(scope)}) {{ edges {{ node {{ path }} }} }} }} }}"
    )
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result.get("errors"), result["errors"]
    return sorted(
        e["node"]["path"] for e in result["data"]["project"]["folders"]["edges"]
    )


def search_ids(
    client: httpx.Client, project: str, field: str, text: str, scope: list[str]
) -> set[str]:
    """Return the ids of the entities (`field`: tasks, ...) found by textSearch."""
    query = (
        f'{{ project(name: "{project}") {{ {field}(textSearch: {json.dumps(text)}, '
        f"textSearchScope: {json.dumps(scope)}) {{ edges {{ node {{ id }} }} }} }} }}"
    )
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result.get("errors"), result["errors"]
    return {e["node"]["id"] for e in result["data"]["project"][field]["edges"]}


def search_until(
    client: httpx.Client, project: str, text: str, scope: list[str], expected: list
) -> None:
    """Search until the expected paths are found (indexing is asynchronous)."""
    found = None
    for _ in range(50):
        if (found := search(client, project, text, scope)) == expected:
            return
        time.sleep(0.2)
    assert found == expected


@pytest.fixture(scope="module")
def tree(api: httpx.Client, temp_project: TempProject) -> Iterator[dict[str, str]]:
    """shots/sh010 with a lighting task, product, version and comment,
    and assets/robot."""
    p = temp_project
    folder_type = p.folder_types[0]
    shots = p.create("folder", name="shots", folderType=folder_type)
    sh010 = p.create("folder", name="sh010", folderType=folder_type, parentId=shots)
    assets = p.create("folder", name="assets", folderType=folder_type)
    robot = p.create("folder", name="robot", folderType=folder_type, parentId=assets)
    task = p.create("task", name="lighting", taskType=p.task_types[0], folderId=sh010)
    product = p.create(
        "product", name="renderLighting", productType="render", folderId=sh010
    )
    version = p.create("version", productId=product, version=1)
    response = api.post(
        f"/api/projects/{p.name}/tasks/{task}/activities",
        json={"activityType": "comment", "body": "needs a retake"},
    )
    assert response.status_code == 201, response.text
    search_until(api, p.name, "retake", ["comment"], ["/shots/sh010"])
    yield {
        "sh010": sh010,
        "robot": robot,
        "task": task,
        "product": product,
        "version": version,
    }


def test_text_search_scopes_and_paths(
    api: httpx.Client, temp_project: TempProject, tree: dict[str, str]
) -> None:
    name = temp_project.name
    assert search(api, name, "sh01", ["folder"]) == ["/shots/sh010"]
    assert search(api, name, "light", ["folder"]) == []
    assert search(api, name, "light", ["task"]) == ["/shots/sh010"]
    # "shots" only matches the path of the task's folder
    assert search(api, name, "shots light", ["task"]) == ["/shots/sh010"]
    assert search(api, name, "sh010, robot", ["folder"]) == [
        "/assets/robot",
        "/shots/sh010",
    ]
    assert search(api, name, "renderLighting v001", ["version"]) == ["/shots/sh010"]
    # Comments do not match by the folder path
    assert search(api, name, "sh010 retake", ["comment"]) == []


def test_text_search_of_tasks_products_versions(
    api: httpx.Client, temp_project: TempProject, tree: dict[str, str]
) -> None:
    name = temp_project.name
    assert search_ids(api, name, "tasks", "shots light", ["task"]) == {tree["task"]}
    assert search_ids(api, name, "tasks", "retake", ["comment"]) == {tree["task"]}
    assert search_ids(api, name, "tasks", "robot", ["task"]) == set()
    products = search_ids(api, name, "products", "sh010 render", ["product"])
    assert products == {tree["product"]}
    # A product is found by its versions
    products = search_ids(api, name, "products", "v001", ["version"])
    assert products == {tree["product"]}
    versions = search_ids(api, name, "versions", "renderLighting v001", ["version"])
    assert versions == {tree["version"]}
    # Scopes which cannot belong to the queried type are rejected
    response = api.post(
        "/graphql",
        json={
            "query": f'{{ project(name: "{name}") {{ tasks(textSearch: "x", '
            'textSearchScope: ["folder"]) { edges { node { id } } } } }'
        },
    )
    assert "Unknown textSearchScope" in response.text


def test_rest_folder_search(
    api: httpx.Client, temp_project: TempProject, tree: dict[str, str]
) -> None:
    """The REST folder search takes the same textSearch as GraphQL."""
    url = f"/api/projects/{temp_project.name}/folders/search"

    def found(payload: dict) -> set[str]:
        response = api.post(url, json=payload)
        assert response.status_code == 200, response.text
        return set(response.json()["folderIds"])

    assert found({"textSearch": "sh01"}) == {tree["sh010"]}
    assert found({"textSearch": "light"}) == set()
    assert found({"textSearch": "light", "textSearchScope": ["task"]}) == {
        tree["sh010"]
    }
    assert found({"textSearch": "sh010, robot"}) == {tree["sh010"], tree["robot"]}
    response = api.post(url, json={"textSearch": "x", "textSearchScope": ["bogus"]})
    assert response.status_code == 400, response.text


def test_text_search_follows_folder_access(
    api: httpx.Client,
    other_user: httpx.Client,
    temp_project: TempProject,
    tree: dict[str, str],
) -> None:
    other_name = other_user.get("/api/users/me").json()["name"]
    group = f"apitest_{uuid.uuid4().hex[:8]}"
    group_url = f"/api/accessGroups/{group}/_"
    access = {"access_type": "hierarchy", "path": "assets"}
    response = api.put(
        group_url, json={"read": {"enabled": True, "access_list": [access]}}
    )
    assert response.status_code == 204, response.text
    try:
        response = api.patch(
            f"/api/users/{other_name}/accessGroups",
            json={
                "accessGroups": [
                    {"project": temp_project.name, "accessGroups": [group]}
                ]
            },
        )
        assert response.status_code == 204, response.text
        name = temp_project.name
        # Access groups reload asynchronously
        search_until(other_user, name, "robot", ["folder"], ["/assets/robot"])
        assert search(other_user, name, "sh010, robot", ["folder"]) == ["/assets/robot"]
        assert search(other_user, name, "light", ["task"]) == []
        assert search(other_user, name, "retake", ["comment"]) == []
    finally:
        api.delete(group_url)


def test_moved_product_takes_its_versions(
    api: httpx.Client, temp_project: TempProject, tree: dict[str, str]
) -> None:
    result = temp_project.op(
        "update", "product", tree["product"], {"folderId": tree["robot"]}
    )
    assert result["success"], result
    search_until(
        api, temp_project.name, "renderLighting v001", ["version"], ["/assets/robot"]
    )
