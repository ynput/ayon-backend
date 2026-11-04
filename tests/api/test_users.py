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


def test_manager_cannot_become_admin(api: httpx.Client) -> None:
    """A manager has no way to gain admin powers."""
    suffix = uuid.uuid4().hex[:8]
    manager, admin, created = f"apitest_m{suffix}", f"apitest_a{suffix}", []
    password = uuid.uuid4().hex + "Aa1!"  # managers get the complexity check

    def create(name: str, **data: object) -> None:
        response = api.put(
            f"/api/users/{name}", json={"password": password, "data": data}
        )
        assert response.status_code == 204, response.text
        created.append(name)

    try:
        create(manager, isManager=True)
        create(admin, isAdmin=True, inviteRequest={"time": 0, "token": "secret"})
        response = httpx.post(
            f"{api.base_url}/api/auth/login",
            json={"name": manager, "password": password},
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['token']}"}
        with httpx.Client(base_url=api.base_url, headers=headers) as client:
            # Creating an admin (or service) user
            name = f"apitest_n{suffix}"
            response = client.put(
                f"/api/users/{name}",
                json={
                    "password": password,
                    "data": {"isAdmin": True, "isService": True},
                },
            )
            assert response.status_code == 204, response.text
            created.append(name)
            data = api.get(f"/api/users/{name}").json()["data"]
            assert not data.get("isAdmin") and not data.get("isService")

            # Making themselves a service user
            response = client.patch(
                f"/api/users/{manager}", json={"data": {"isService": True}}
            )
            assert response.status_code == 204, response.text
            data = api.get(f"/api/users/{manager}").json()["data"]
            assert not data.get("isService")

            # Taking over an admin
            response = client.patch(
                f"/api/users/{admin}/password", json={"password": password + "X"}
            )
            assert response.status_code == 403, response.text
            assert client.delete(f"/api/users/{admin}").status_code == 403

            # Reading an admin's invite token
            response = client.get(f"/api/users/{admin}")
            assert response.status_code == 200, response.text
            assert "inviteRequest" not in response.json()["data"]
    finally:
        for name in created:
            api.delete(f"/api/users/{name}")
