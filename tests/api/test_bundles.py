"""Bundles REST endpoints.

The tests create their own (non-production, non-staging) bundles
and delete them afterwards, so the bundles of the server are not affected.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest


def get_bundle(api: httpx.Client, name: str) -> dict[str, Any]:
    response = api.get("/api/bundles", params={"archived": True})
    assert response.status_code == 200, response.text
    for bundle in response.json()["bundles"]:
        if bundle["name"] == name:
            return bundle
    raise AssertionError(f"Bundle {name} not found")


def patch_bundle(api: httpx.Client, name: str, data: dict[str, Any]) -> None:
    response = api.patch(f"/api/bundles/{name}", json=data, params={"force": True})
    assert response.status_code == 204, response.text


@pytest.fixture
def bundle_name(api: httpx.Client) -> Iterator[str]:
    """Name of a bundle to create (deleted afterwards)."""
    name = f"apitest_{uuid.uuid4().hex[:8]}"
    yield name
    api.delete(f"/api/bundles/{name}")


def create_bundle(api: httpx.Client, name: str, **data: Any) -> dict[str, Any]:
    response = api.post(
        "/api/bundles",
        json={"name": name, "addons": {}, **data},
        params={"force": True},
    )
    assert response.status_code == 201, response.text
    return get_bundle(api, name)


def test_create_shape(api: httpx.Client, bundle_name: str):
    bundle = create_bundle(api, bundle_name)
    assert bundle["description"] is None
    assert bundle["isProject"] is False
    assert bundle["dependencyPackages"] == {}
    assert bundle["updatedAt"]
    assert bundle["createdAt"]


def test_create_with_data(api: httpx.Client, bundle_name: str):
    bundle = create_bundle(
        api,
        bundle_name,
        description="Created by API tests",
        dependencyPackages={"windows": "nonexistent.zip"},
    )
    assert bundle["description"] == "Created by API tests"
    assert bundle["dependencyPackages"] == {"windows": "nonexistent.zip"}


def test_create_invalid_platform(api: httpx.Client, bundle_name: str):
    response = api.post(
        "/api/bundles",
        json={"name": bundle_name, "dependencyPackages": {"amiga": "a.zip"}},
        params={"force": True},
    )
    assert response.status_code == 400, response.text


def test_patch_description(api: httpx.Client, bundle_name: str):
    created = create_bundle(api, bundle_name, description="Original")

    # Patching other fields keeps the description
    patch_bundle(api, bundle_name, {"isArchived": True})
    bundle = get_bundle(api, bundle_name)
    assert bundle["isArchived"] is True
    assert bundle["description"] == "Original"

    patch_bundle(api, bundle_name, {"description": "Changed"})
    assert get_bundle(api, bundle_name)["description"] == "Changed"

    # Explicit null clears it
    patch_bundle(api, bundle_name, {"description": None})
    bundle = get_bundle(api, bundle_name)
    assert bundle["description"] is None
    assert bundle["createdAt"] == created["createdAt"]


def test_patch_updates_timestamp(api: httpx.Client, bundle_name: str):
    created = create_bundle(api, bundle_name)
    time.sleep(0.01)
    patch_bundle(api, bundle_name, {"description": "Changed"})
    bundle = get_bundle(api, bundle_name)
    updated_at = datetime.fromisoformat(bundle["updatedAt"])
    assert updated_at > datetime.fromisoformat(created["updatedAt"])
    assert bundle["createdAt"] == created["createdAt"]
