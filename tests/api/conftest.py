"""API tests run against a running AYON server using HTTP only.

    AYON_API_URL=http://localhost:5000 AYON_API_KEY=... make test-api

`AYON_API_TEST_PROJECT` selects the project to test with (by default
the first project with folders and tasks). The tests only read data,
or create temporary data using the API, which they delete. Tests changing
entities use a temporary project (`temp_project`). They are skipped
when the server is not available.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

API_URL = os.environ.get("AYON_API_URL", "http://localhost:5000")
API_KEY = os.environ.get("AYON_API_KEY", "")

GraphQL = Callable[[str], dict[str, Any]]


@pytest.fixture(scope="session")
def api() -> Iterator[httpx.Client]:
    """HTTP client of the tested server (authenticated as an admin)."""
    client = httpx.Client(
        base_url=API_URL,
        headers={"x-api-key": API_KEY},
        timeout=120,
    )
    try:
        response = client.get("/api/users/me")
    except httpx.HTTPError as e:
        pytest.skip(f"Server {API_URL} is not available: {e}")
    if response.status_code != 200:
        pytest.skip(f"Unable to log in to {API_URL} ({response.status_code})")
    data = response.json().get("data", {})
    if not (data.get("isAdmin") or data.get("isService")):
        pytest.skip("API tests require an admin (or service) API key")
    yield client
    client.close()


@pytest.fixture(scope="session")
def graphql(api: httpx.Client) -> GraphQL:
    """Execute a GraphQL query, return its data (fails on errors)."""

    def execute(query: str) -> dict[str, Any]:
        response = api.post("/graphql", json={"query": query})
        assert response.status_code == 200, response.text
        result = response.json()
        assert not result.get("errors"), result["errors"]
        return result["data"]

    return execute


@pytest.fixture(scope="session")
def project_name(api: httpx.Client, graphql: GraphQL) -> str:
    """Name of a project with folders and tasks."""
    if name := os.environ.get("AYON_API_TEST_PROJECT"):
        return name
    for project in api.get("/api/projects").json()["projects"]:
        name = project["name"]
        data = graphql(
            f'{{ project(name: "{name}") {{ folders(first: 1) '
            "{ edges { node { id } } } tasks(first: 1) { edges { node { id } } } } }"
        )
        if data["project"]["folders"]["edges"] and data["project"]["tasks"]["edges"]:
            return project["name"]
    pytest.skip("No project with folders and tasks")


#
# Temporary project
#


def operation(
    type: str,
    entity_type: str,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Return an operation of the operations endpoint."""
    op: dict[str, Any] = {"type": type, "entityType": entity_type, **kwargs}
    if entity_id is not None:
        op["entityId"] = entity_id
    if data is not None:
        op["data"] = data
    return op


@dataclass
class TempProject:
    """A project created for the tests (deleted afterwards)."""

    api: httpx.Client
    name: str
    folder_types: list[str] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)

    def ops(self, *operations: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Process operations, return the response of the endpoint."""
        response = self.api.post(
            f"/api/projects/{self.name}/operations",
            json={"operations": list(operations), **kwargs},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def op(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Process a single operation, return its result."""
        result = self.ops(operation(*args, **kwargs))
        return result["operations"][0]

    def create(self, entity_type: str, **data: Any) -> str:
        """Create an entity (the operation must succeed), return its ID."""
        result = self.op("create", entity_type, data=data)
        assert result["success"], result
        return result["entityId"]

    def get(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        """Return an entity using the REST API."""
        response = self.api.get(f"/api/projects/{self.name}/{entity_type}s/{entity_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def exists(self, entity_type: str, entity_id: str) -> bool:
        url = f"/api/projects/{self.name}/{entity_type}s/{entity_id}"
        return self.api.get(url).status_code == 200


@contextmanager
def create_temp_project(api: httpx.Client) -> Iterator[TempProject]:
    """Create a project with the default anatomy, delete it afterwards."""
    name = f"apitest_{uuid.uuid4().hex[:8]}"
    response = api.post("/api/projects", json={"name": name, "code": name[-8:]})
    assert response.status_code == 201, response.text
    try:
        project = api.get(f"/api/projects/{name}").json()
        yield TempProject(
            api=api,
            name=name,
            folder_types=[t["name"] for t in project["folderTypes"]],
            task_types=[t["name"] for t in project["taskTypes"]],
            statuses=[s["name"] for s in project["statuses"]],
        )
    finally:
        api.delete(f"/api/projects/{name}")


@pytest.fixture(scope="module")
def temp_project(api: httpx.Client) -> Iterator[TempProject]:
    """A new project with the default anatomy (one per test module)."""
    with create_temp_project(api) as project:
        yield project
