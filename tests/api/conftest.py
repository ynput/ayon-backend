"""API tests run against a running AYON server using HTTP only.

    AYON_API_URL=http://localhost:5000 AYON_API_KEY=... make test-api

`AYON_API_TEST_PROJECT` selects the project to test with (by default
the first project with folders and tasks). The tests only read data,
or create temporary data using the API, which they delete. They are
skipped when the server is not available.
"""

import os
from collections.abc import Callable, Iterator
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
