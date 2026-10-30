"""User endpoints (/api/users)."""

import uuid

import httpx


def test_get_user_hides_secrets(api: httpx.Client) -> None:
    """Reading another user never returns data that allows logging in as them."""
    name = f"apitest_{uuid.uuid4().hex[:8]}"
    response = api.put(f"/api/users/{name}", json={"password": uuid.uuid4().hex})
    assert response.status_code == 204, response.text
    try:
        response = api.get(f"/api/users/{name}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        for key in ("password", "apiKey", "apiKeys", "passwordResetRequest"):
            assert key not in data
    finally:
        api.delete(f"/api/users/{name}")
