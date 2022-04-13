from fastapi.testclient import TestClient

from openpype.api import app


class API:
    def __init__(self, access_token):
        self.client = TestClient(app)
        self.access_token = access_token

    @classmethod
    def login(cls, username: str, password: str) -> "API":
        client = TestClient(app)
        response = client.post(
            "/api/auth/login", json={"name": username, "password": password}
        )
        r = response.json()
        assert r["user"]["name"] == username
        return cls(r["token"])

    def get(self, path: str, **kwargs):
        response = self.client.get(
            path, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
        )
        assert response.status_code == 200
        return response.json()

    def post(self, path: str, **kwargs):
        response = self.client.post(
            path, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
        )
        assert response.status_code < 400
        return response.json()

    def put(self, path: str, **kwargs):
        return self.client.put(
            path, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
        )

    def delete(self, path: str, **kwargs):
        return self.client.delete(
            path, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
        )

    def patch(self, path: str, **kwargs):
        return self.client.patch(
            path, headers={"Authorization": f"Bearer {self.access_token}"}, **kwargs
        )
