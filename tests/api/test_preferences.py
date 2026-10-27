"""Private preferences of the current user (/api/preferences)."""

import uuid
from collections.abc import Iterator

import httpx
import pytest

from .conftest import API_URL, create_temp_project

KEY = "io.ynput.test.preferences"


def new_key() -> str:
    return f"{KEY}.{uuid.uuid4().hex[:8]}"


@pytest.fixture
def key(api: httpx.Client) -> Iterator[str]:
    """A unique preference key, removed after the test."""
    key = new_key()
    yield key
    api.delete(f"/api/preferences/{key}")


@pytest.fixture(scope="module")
def other_user(api: httpx.Client) -> Iterator[httpx.Client]:
    """Client logged in as a new (non-manager) user, deleted afterwards."""
    name = f"apitest_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    response = api.put(f"/api/users/{name}", json={"password": password})
    assert response.status_code == 204, response.text
    try:
        response = httpx.post(
            f"{API_URL}/api/auth/login", json={"name": name, "password": password}
        )
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        with httpx.Client(
            base_url=API_URL, headers={"Authorization": f"Bearer {token}"}
        ) as client:
            yield client
    finally:
        api.delete(f"/api/users/{name}")


@pytest.fixture(scope="module")
def temp_project_name(api: httpx.Client) -> Iterator[str]:
    with create_temp_project(api) as project:
        yield project.name


def test_crud(api: httpx.Client, key: str) -> None:
    url = f"/api/preferences/{key}"
    assert api.get(url).status_code == 404

    response = api.put(url, json={"a": 1, "b": {"c": 2}})
    assert response.status_code == 204, response.text
    pref = api.get(url).json()
    assert pref["key"] == key
    assert pref["projectName"] is None
    assert pref["data"] == {"a": 1, "b": {"c": 2}}

    # PATCH is a shallow merge
    response = api.patch(url, json={"b": {"d": 3}, "e": 4})
    assert response.status_code == 204, response.text
    assert api.get(url).json()["data"] == {"a": 1, "b": {"d": 3}, "e": 4}

    # PUT replaces the data
    assert api.put(url, json={"x": True}).status_code == 204
    assert api.get(url).json()["data"] == {"x": True}

    assert api.delete(url).status_code == 204
    assert api.get(url).status_code == 404
    assert api.delete(url).status_code == 404


def test_patch_creates(api: httpx.Client, key: str) -> None:
    url = f"/api/preferences/{key}"
    assert api.patch(url, json={"a": 1}).status_code == 204
    assert api.get(url).json()["data"] == {"a": 1}


def test_invalid(api: httpx.Client) -> None:
    assert api.put("/api/preferences/.invalid", json={}).status_code == 400
    assert api.put(f"/api/preferences/{KEY}", json=[1, 2]).status_code == 400
    url = f"/api/preferences/{KEY}?project_name=not_existing_project_name"
    assert api.put(url, json={}).status_code == 404


def test_size_limit(api: httpx.Client, key: str) -> None:
    url = f"/api/preferences/{key}"
    half = "x" * (150 * 1024)
    assert api.put(url, json={"a": half}).status_code == 204
    # The limit applies to the merged data
    assert api.patch(url, json={"b": half}).status_code == 400
    assert api.get(url).json()["data"] == {"a": half}


def test_list(api: httpx.Client) -> None:
    prefix = f"{new_key()}."
    keys = [f"{prefix}b", f"{prefix}a"]
    try:
        for key in keys:
            assert api.put(f"/api/preferences/{key}", json={}).status_code == 204
        response = api.get("/api/preferences", params={"key_prefix": prefix})
        assert response.status_code == 200, response.text
        listed = [p["key"] for p in response.json()["preferences"]]
        assert listed == sorted(keys)
    finally:
        for key in keys:
            api.delete(f"/api/preferences/{key}")


def test_project_scope(api: httpx.Client, key: str) -> None:
    url = f"/api/preferences/{key}"
    with create_temp_project(api) as project:
        params = {"project_name": project.name}
        assert api.put(url, json={"scope": "global"}).status_code == 204
        assert api.put(url, params=params, json={"scope": "project"}).status_code == 204

        assert api.get(url).json()["data"] == {"scope": "global"}
        pref = api.get(url, params=params).json()
        assert pref["projectName"] == project.name
        assert pref["data"] == {"scope": "project"}

        response = api.get("/api/preferences", params={**params, "key_prefix": key})
        assert [p["projectName"] for p in response.json()["preferences"]] == [
            project.name
        ]

    # Removed with the project, the global one is kept
    assert api.get(url, params=params).status_code == 404
    assert api.get(url).json()["data"] == {"scope": "global"}


def test_private(api: httpx.Client, other_user: httpx.Client, key: str) -> None:
    url = f"/api/preferences/{key}"
    assert api.put(url, json={"owner": "admin"}).status_code == 204

    # The other user has their own preference under the same key
    assert other_user.get(url).status_code == 404
    assert other_user.put(url, json={"owner": "other"}).status_code == 204
    assert other_user.get(url).json()["data"] == {"owner": "other"}
    assert api.get(url).json()["data"] == {"owner": "admin"}

    assert other_user.delete(url).status_code == 204
    assert api.get(url).json()["data"] == {"owner": "admin"}


def test_project_access(other_user: httpx.Client, temp_project_name: str) -> None:
    url = f"/api/preferences/{new_key()}?project_name={temp_project_name}"
    assert other_user.put(url, json={}).status_code == 403
