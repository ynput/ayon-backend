"""The server URL used in emails is learned only from administrators."""

import uuid
from collections.abc import Iterator

import httpx
import pytest

from .conftest import API_URL


def get_server_url(api: httpx.Client) -> str:
    response = api.get("/api/config/value/server_url")
    assert response.status_code == 200, response.text
    return response.json()


def set_server_url(api: httpx.Client, value: str) -> None:
    response = api.patch("/api/config", json={"server_url": value})
    assert response.status_code == 204, response.text


@pytest.fixture
def admin_user(api: httpx.Client) -> Iterator[httpx.Client]:
    """Client logged in as a new (human) administrator, deleted afterwards."""
    name = f"apitest_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    payload = {"password": password, "data": {"isAdmin": True}}
    response = api.put(f"/api/users/{name}", json=payload)
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


def test_server_url_from_admin_only(
    api: httpx.Client,
    other_user: httpx.Client,
    admin_user: httpx.Client,
) -> None:
    original = get_server_url(api)
    set_server_url(api, "")
    try:
        # A normal user can't decide where links sent by the server point to
        other_user.get("/api/info", headers={"referer": "https://evil.test/"})
        assert get_server_url(api) == ""

        admin_user.get("/api/info", headers={"referer": "https://ayon.test/projects"})
        assert get_server_url(api) == "https://ayon.test"

        # Once set, it is kept
        admin_user.get("/api/info", headers={"referer": "https://other.test/"})
        assert get_server_url(api) == "https://ayon.test"
    finally:
        set_server_url(api, original)
