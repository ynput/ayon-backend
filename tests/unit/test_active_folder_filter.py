"""Folder-list filtering through the HTTP endpoint.

Load this module by filename to avoid api.folders importing the GraphQL schema.
The import-time attribute database load is mocked. Requests use the real
endpoint, router, response builder, JSON serializer, and access checker, with
user/project validation and data loading supplied by fixtures.
"""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def list_folders():
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(BACKEND_DIR))
        from ayon_server.lib.postgres import Postgres

        # Treat the module as a package so its relative .router import works.
        spec = importlib.util.spec_from_file_location(
            "_test_folder_list",
            BACKEND_DIR / "api" / "folders" / "list_folders.py",
            submodule_search_locations=[str(BACKEND_DIR / "api" / "folders")],
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        mp.setitem(sys.modules, spec.name, module)
        try:
            with (
                patch.object(Postgres, "connect", new_callable=AsyncMock),
                patch.object(
                    Postgres, "fetch", new_callable=AsyncMock, return_value=[]
                ),
                patch.object(Postgres, "shutdown", new_callable=AsyncMock),
            ):
                spec.loader.exec_module(module)
            yield module
        finally:
            sys.modules.pop(f"{spec.name}.router", None)
            if hasattr(module, "folder_list_loader"):
                module.folder_list_loader._executor.shutdown()


@pytest.fixture
def folders():
    return [
        {
            "id": path,
            "path": path,
            "active": active,
            "visible": visible,
            "attrib": {"fps": 24, "description": "Example"},
            "ownAttrib": ["fps", "description"],
        }
        for path, active, visible in [
            ("shots", True, True),
            ("shots/active", True, True),
            ("shots/inactive", False, True),
            ("archived", False, False),
            ("archived/child", True, False),
            ("archived/child/grandchild", True, False),
            ("restricted", True, True),
            ("restricted/inactive", False, False),
        ]
    ]


@pytest.fixture
def user():
    return SimpleNamespace(is_guest=False, is_manager=True)


@pytest.fixture
def client(list_folders, folders, user, monkeypatch):
    from ayon_server.api.dependencies import dep_current_user, dep_project_name

    async def load_access(self, user, project_name, access_type):
        self.exact_paths = {
            folder["path"]
            for folder in folders
            if not folder["path"].startswith("restricted")
        }

    monkeypatch.setattr(list_folders.AccessChecker, "load", load_access)
    monkeypatch.setattr(
        list_folders.folder_list_loader,
        "get_folder_list",
        AsyncMock(return_value=folders),
    )
    app = FastAPI()
    app.dependency_overrides[dep_current_user] = lambda: user
    app.dependency_overrides[dep_project_name] = lambda: "testproject"
    app.include_router(list_folders.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "params,expected",
    [
        (
            {},
            [
                "shots",
                "shots/active",
                "shots/inactive",
                "archived",
                "archived/child",
                "archived/child/grandchild",
            ],
        ),
        ({"visibility": "visible"}, ["shots", "shots/active"]),
        (
            {"visibility": "hidden"},
            [
                "shots/inactive",
                "archived",
                "archived/child",
                "archived/child/grandchild",
            ],
        ),
    ],
)
def test_visibility_filter(client, folders, params, expected):
    original = deepcopy(folders)
    response = client.get("/projects/testproject/folders", params=params)

    assert response.status_code == 200
    result = response.json()["folders"]
    assert [folder["path"] for folder in result] == expected
    assert all(
        "attrib" not in folder and "ownAttrib" not in folder for folder in result
    )
    assert folders == original


def test_visibility_all_matches_default(client):
    default_response = client.get("/projects/testproject/folders")
    all_response = client.get(
        "/projects/testproject/folders",
        params={"visibility": "all"},
    )

    assert default_response.status_code == 200
    assert all_response.status_code == 200
    assert all_response.json() == default_response.json()


def test_invalid_visibility_parameter(client):
    response = client.get(
        "/projects/testproject/folders", params={"visibility": "invalid"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("is_manager", [True, False])
def test_visibility_filter_with_attributes(client, folders, user, is_manager):
    original = deepcopy(folders)
    user.is_manager = is_manager
    user.permissions = lambda **kwargs: SimpleNamespace(
        attrib_read=SimpleNamespace(enabled=True, attributes=["fps"])
    )
    response = client.get(
        "/projects/testproject/folders",
        params={"visibility": "visible", "attrib": "true"},
    )

    assert response.status_code == 200
    result = response.json()["folders"]
    assert [folder["path"] for folder in result] == ["shots", "shots/active"]
    expected_attrib = (
        {"fps": 24, "description": "Example"} if is_manager else {"fps": 24}
    )
    for folder in result:
        assert folder["attrib"] == expected_attrib
        assert folder["ownAttrib"] == list(expected_attrib)
    assert folders == original


def test_guest_still_receives_no_folders(client, user, list_folders):
    user.is_guest = True
    response = client.get(
        "/projects/testproject/folders", params={"visibility": "visible"}
    )

    assert response.status_code == 200
    assert response.json()["folders"] == []
    list_folders.folder_list_loader.get_folder_list.assert_not_awaited()
