"""The folder list (`GET /folders`) is cached in Redis, so it must be
invalidated by every write it shows. Each test reads the list first to make
sure the cache is warm, then writes and checks the list again.
"""

import base64
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from .conftest import TempProject, create_temp_project

# 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def project(api: httpx.Client) -> Iterator[TempProject]:
    with create_temp_project(api) as project:
        yield project


def folder_list(project: TempProject) -> dict[str, dict[str, Any]]:
    response = project.api.get(
        f"/api/projects/{project.name}/folders", params={"attrib": "true"}
    )
    assert response.status_code == 200, response.text
    return {f["id"]: f for f in response.json()["folders"]}


def patch_project(project: TempProject, data: dict[str, Any]) -> None:
    response = project.api.patch(f"/api/projects/{project.name}", json=data)
    assert response.status_code == 204, response.text


def rename_first(project: TempProject, key: str) -> str:
    types = project.api.get(f"/api/projects/{project.name}").json()[key]
    old = types[0]["name"]
    types[0] = {**types[0], "name": f"{old}Renamed", "original_name": old}
    patch_project(project, {key: types})
    return f"{old}Renamed"


def create_folder(project: TempProject, **data: Any) -> str:
    return project.create(
        "folder",
        name=data.pop("name", "shot"),
        folderType=project.folder_types[0],
        status=project.statuses[0],
        **data,
    )


def test_project_attrib_change(project: TempProject):
    folder_id = create_folder(project)
    width = folder_list(project)[folder_id]["attrib"]["resolutionWidth"]

    patch_project(project, {"attrib": {"resolutionWidth": width + 1}})
    assert folder_list(project)[folder_id]["attrib"]["resolutionWidth"] == width + 1


def test_own_attrib_overrides_project_change(project: TempProject):
    folder_id = create_folder(project, attrib={"resolutionWidth": 123})
    folder_list(project)

    patch_project(project, {"attrib": {"resolutionWidth": 456}})
    assert folder_list(project)[folder_id]["attrib"]["resolutionWidth"] == 123


def test_project_save_without_changes(project: TempProject):
    folder_id = create_folder(project)
    before = folder_list(project)[folder_id]

    patch_project(project, {"active": True})
    assert folder_list(project)[folder_id] == before


@pytest.mark.parametrize(
    "key, field", [("folderTypes", "folderType"), ("statuses", "status")]
)
def test_aux_type_rename(project: TempProject, key: str, field: str):
    folder_id = create_folder(project)
    folder_list(project)

    new_name = rename_first(project, key)
    assert folder_list(project)[folder_id][field] == new_name


def test_folder_update(project: TempProject):
    folder_id = create_folder(project)
    folder_list(project)

    result = project.op(
        "update", "folder", folder_id, data={"label": "Shot", "attrib": {"fps": 50}}
    )
    assert result["success"], result
    folder = folder_list(project)[folder_id]
    assert folder["label"] == "Shot"
    assert folder["attrib"]["fps"] == 50


def test_child_folder_create(project: TempProject):
    parent_id = create_folder(project)
    assert not folder_list(project)[parent_id]["hasChildren"]

    child_id = create_folder(project, name="sub", parentId=parent_id)
    folders = folder_list(project)
    assert folders[parent_id]["hasChildren"]
    assert folders[child_id]["parentId"] == parent_id


def test_task_create(project: TempProject):
    folder_id = create_folder(project)
    assert not folder_list(project)[folder_id]["hasTasks"]

    project.create(
        "task", name="comp", taskType=project.task_types[0], folderId=folder_id
    )
    folder = folder_list(project)[folder_id]
    assert folder["hasTasks"]
    assert folder["taskNames"] == ["comp"]


# REST writes commit after `refresh_views` ran (inside their transaction)


def test_task_rest_update(project: TempProject):
    folder_id = create_folder(project)
    task_id = project.create(
        "task", name="comp", taskType=project.task_types[0], folderId=folder_id
    )
    assert folder_list(project)[folder_id]["taskNames"] == ["comp"]

    response = project.api.patch(
        f"/api/projects/{project.name}/tasks/{task_id}", json={"name": "light"}
    )
    assert response.status_code == 204, response.text
    assert folder_list(project)[folder_id]["taskNames"] == ["light"]


def test_folder_thumbnail(project: TempProject):
    folder_id = create_folder(project)
    before = folder_list(project)[folder_id]["thumbnailHash"]

    response = project.api.post(
        f"/api/projects/{project.name}/folders/{folder_id}/thumbnail",
        content=PNG,
        headers={"content-type": "image/png"},
    )
    assert response.status_code == 200, response.text
    after = folder_list(project)[folder_id]["thumbnailHash"]
    assert after != before

    # Updating the thumbnail by its ID saves no entity
    response = project.api.put(
        f"/api/projects/{project.name}/thumbnails/{response.json()['id']}",
        content=PNG,
        headers={"content-type": "image/png"},
    )
    assert response.status_code == 200, response.text
    assert folder_list(project)[folder_id]["thumbnailHash"] != after


def test_reviewable_upload(project: TempProject):
    folder_id = create_folder(project)
    product_id = project.create(
        "product", name="review", folderId=folder_id, productType="review"
    )
    version_id = project.create("version", productId=product_id, version=1)
    assert not folder_list(project)[folder_id]["hasReviewables"]

    response = project.api.post(
        f"/api/projects/{project.name}/versions/{version_id}/reviewables",
        content=PNG,
        headers={"x-file-name": "review.png", "content-type": "image/png"},
    )
    assert response.status_code == 200, response.text
    assert folder_list(project)[folder_id]["hasReviewables"]
