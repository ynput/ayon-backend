"""Hover-scrub filmstrips of reviewables (file and entity endpoints)."""

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from .conftest import TempProject

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg is not available"
)


def name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def make_video(path: Path) -> bytes:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=25:duration=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


@dataclass
class Hierarchy:
    project: TempProject
    folder_id: str
    task_id: str
    version_id: str  # with a video reviewable
    file_id: str  # the video reviewable
    empty_version_id: str  # without reviewables


@pytest.fixture(scope="module")
def hierarchy(temp_project: TempProject, tmp_path_factory) -> Hierarchy:
    project = temp_project
    folder_id = project.create(
        "folder", name=name("folder"), folderType=project.folder_types[0]
    )
    task_id = project.create(
        "task", name=name("task"), folderId=folder_id, taskType=project.task_types[0]
    )
    product_id = project.create(
        "product", name=name("product"), folderId=folder_id, productType="review"
    )
    version_id = project.create(
        "version", productId=product_id, version=1, taskId=task_id
    )
    empty_version_id = project.create("version", productId=product_id, version=2)

    video = make_video(tmp_path_factory.mktemp("filmstrip") / "review.mp4")
    response = project.api.post(
        f"/api/projects/{project.name}/versions/{version_id}/reviewables",
        content=video,
        headers={"x-file-name": "review.mp4", "content-type": "video/mp4"},
    )
    assert response.status_code == 200, response.text

    return Hierarchy(
        project=project,
        folder_id=folder_id,
        task_id=task_id,
        version_id=version_id,
        file_id=response.json()["fileId"],
        empty_version_id=empty_version_id,
    )


def get_filmstrip(h: Hierarchy, path: str, **params: Any):
    return h.project.api.get(f"/api/projects/{h.project.name}/{path}", params=params)


def test_file_filmstrip(hierarchy: Hierarchy):
    response = get_filmstrip(hierarchy, f"files/{hierarchy.file_id}/filmstrip")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["fileId"] == hierarchy.file_id
    assert data["frames"] >= 2
    assert data["columns"] >= 1
    # fits the frame size box, keeps the aspect ratio of the 320x180 video
    assert abs(data["frameWidth"] / data["frameHeight"] - 16 / 9) < 0.05


@pytest.mark.parametrize("entity", ["version", "task", "folder"])
def test_entity_filmstrip_uses_latest_reviewable(hierarchy: Hierarchy, entity: str):
    entity_id = getattr(hierarchy, f"{entity}_id")
    response = get_filmstrip(hierarchy, f"{entity}s/{entity_id}/filmstrip")
    assert response.status_code == 200, response.text
    assert response.json()["fileId"] == hierarchy.file_id


def test_entity_without_reviewable(hierarchy: Hierarchy):
    path = f"versions/{hierarchy.empty_version_id}/filmstrip"
    response = get_filmstrip(hierarchy, path)
    assert response.status_code == 204
    assert "max-age" in response.headers["Cache-Control"]
    assert get_filmstrip(hierarchy, path, placeholder="none").status_code == 404


def test_payload(hierarchy: Hierarchy):
    api = hierarchy.project.api
    data = get_filmstrip(hierarchy, f"files/{hierarchy.file_id}/filmstrip").json()

    response = api.get(data["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/avif"
    assert "immutable" in response.headers["Cache-Control"]
    assert response.content

    # without a version, the image may change
    url = f"/api/projects/{hierarchy.project.name}/files/{hierarchy.file_id}"
    response = api.get(f"{url}/filmstrip/payload")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-cache"

    # the image of another version would not match its layout
    response = api.get(f"{url}/filmstrip/payload", params={"v": "0.0.0"})
    assert response.status_code == 404
