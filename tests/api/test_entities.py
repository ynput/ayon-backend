"""Projects and users CRUD (REST endpoints).

Project-level entities are covered by test_operations.py.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from .conftest import TempProject

#
# Projects
#


class TestProjects:
    @pytest.fixture
    def project(self, temp_project: TempProject) -> TempProject:
        return temp_project

    def get(self, project: TempProject) -> dict[str, Any]:
        return project.api.get(f"/api/projects/{project.name}").json()

    def patch(self, project: TempProject, data: dict[str, Any]) -> httpx.Response:
        return project.api.patch(f"/api/projects/{project.name}", json=data)

    def test_new_project_has_the_default_attributes(self, project: TempProject):
        attributes = project.api.get("/api/attributes").json()["attributes"]
        defaults = {
            a["name"]: a["data"]["default"]
            for a in attributes
            if "project" in a["scope"] and a["data"].get("default") is not None
        }
        attrib = self.get(project)["attrib"]
        for key, value in defaults.items():
            assert attrib[key] == value, key

    def test_patch(self, project: TempProject):
        response = self.patch(project, {"label": "API test", "library": True})
        assert response.status_code == 204, response.text
        data = self.get(project)
        assert data["label"] == "API test"
        assert data["library"] is True

    def test_patch_attributes(self, project: TempProject):
        assert self.patch(project, {"attrib": {"fps": 50}}).status_code == 204
        assert self.get(project)["attrib"]["fps"] == 50.0
        assert self.patch(project, {"attrib": {"fps": "fast"}}).status_code == 400
        assert self.get(project)["attrib"]["fps"] == 50.0

    def test_patch_data(self, project: TempProject):
        assert self.patch(project, {"data": {"a": 1, "b": 2}}).status_code == 204
        assert self.patch(project, {"data": {"a": None, "c": 3}}).status_code == 204
        data = self.get(project)["data"]
        assert "a" not in data
        assert data["b"] == 2 and data["c"] == 3

    def test_anatomy_attributes(self, project: TempProject):
        url = f"/api/projects/{project.name}/anatomy"
        anatomy = project.api.get(url).json()
        anatomy["attributes"]["resolutionWidth"] = 4096
        assert project.api.post(url, json=anatomy).status_code == 204
        assert self.get(project)["attrib"]["resolutionWidth"] == 4096

        anatomy["attributes"]["resolutionWidth"] = "wide"
        assert project.api.post(url, json=anatomy).status_code == 400

    def test_duplicate_name(self, project: TempProject):
        response = project.api.post(
            "/api/projects", json={"name": project.name, "code": "dup"}
        )
        assert response.status_code == 409

    def test_invalid_name(self, api: httpx.Client):
        response = api.post("/api/projects", json={"name": "not valid!", "code": "x"})
        assert response.status_code == 400

    def test_delete(self, api: httpx.Client):
        name = f"apitest_{uuid.uuid4().hex[:8]}"
        assert (
            api.post(
                "/api/projects", json={"name": name, "code": name[-8:]}
            ).status_code
            == 201
        )
        assert api.delete(f"/api/projects/{name}").status_code == 204
        assert api.get(f"/api/projects/{name}").status_code == 404


#
# Users
#


class TestUsers:
    @pytest.fixture
    def user_name(self, api: httpx.Client) -> Iterator[str]:
        name = f"apitest{uuid.uuid4().hex[:8]}"
        response = api.put(
            f"/api/users/{name}",
            json={"attrib": {"fullName": "API Test"}, "password": "Api-test-1234!"},
        )
        assert response.status_code == 204, response.text
        yield name
        api.delete(f"/api/users/{name}")

    def get(self, api: httpx.Client, name: str) -> dict[str, Any]:
        response = api.get(f"/api/users/{name}")
        assert response.status_code == 200, response.text
        return response.json()

    def test_create(self, api: httpx.Client, user_name: str):
        data = self.get(api, user_name)
        assert data["name"] == user_name
        assert data["attrib"]["fullName"] == "API Test"
        assert data["active"] is True

    def test_patch(self, api: httpx.Client, user_name: str):
        response = api.patch(
            f"/api/users/{user_name}",
            json={"attrib": {"email": "api@example.com"}, "active": False},
        )
        assert response.status_code == 204, response.text
        data = self.get(api, user_name)
        assert data["attrib"]["email"] == "api@example.com"
        assert data["attrib"]["fullName"] == "API Test"  # not modified
        assert data["active"] is False

    def test_patch_without_data(self, api: httpx.Client, user_name: str):
        # data: null means "not modified"
        response = api.patch(f"/api/users/{user_name}", json={"data": None})
        assert response.status_code == 204, response.text

    def test_null_data_is_rejected_on_create(self, api: httpx.Client):
        name = f"apitest{uuid.uuid4().hex[:8]}"
        response = api.put(f"/api/users/{name}", json={"data": None})
        assert response.status_code == 400
        assert api.get(f"/api/users/{name}").status_code == 404

    def test_duplicate_name(self, api: httpx.Client, user_name: str):
        response = api.put(f"/api/users/{user_name}", json={})
        assert response.status_code == 409

    def test_delete(self, api: httpx.Client, user_name: str):
        assert api.delete(f"/api/users/{user_name}").status_code == 204
        assert api.get(f"/api/users/{user_name}").status_code == 404
