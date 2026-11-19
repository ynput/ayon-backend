"""Custom data of reviewables (stored in file data)."""

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

OVERLAY = {
    "schema": "test/1",
    "frames": 25,
    "perFrame": {"value": [[0, 9, "a"], [10, 24, "b"]]},
}


@dataclass
class Reviewable:
    project: TempProject
    version_id: str
    other_version_id: str
    activity_id: str
    file_id: str

    @property
    def url(self) -> str:
        return (
            f"/api/projects/{self.project.name}/versions/{self.version_id}"
            f"/reviewables/{self.activity_id}"
        )

    def patch(self, payload: dict[str, Any], url: str | None = None):
        return self.project.api.patch(url or self.url, json=payload)

    def listed(self) -> dict[str, Any]:
        response = self.project.api.get(
            f"/api/projects/{self.project.name}/versions/{self.version_id}/reviewables"
        )
        assert response.status_code == 200, response.text
        for item in response.json()["reviewables"]:
            if item["fileId"] == self.file_id:
                return item
        raise AssertionError("Reviewable not listed")


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
            "testsrc=size=320x180:rate=25:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


@pytest.fixture(scope="module")
def reviewable(temp_project: TempProject, tmp_path_factory) -> Reviewable:
    project = temp_project
    folder_id = project.create(
        "folder",
        name=f"folder_{uuid.uuid4().hex[:8]}",
        folderType=project.folder_types[0],
    )
    product_id = project.create(
        "product", name="review", folderId=folder_id, productType="review"
    )
    version_id = project.create("version", productId=product_id, version=1)
    other_version_id = project.create("version", productId=product_id, version=2)

    video = make_video(tmp_path_factory.mktemp("overlay") / "review.mp4")
    response = project.api.post(
        f"/api/projects/{project.name}/versions/{version_id}/reviewables",
        content=video,
        headers={"x-file-name": "review.mp4", "content-type": "video/mp4"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["data"] == {}
    return Reviewable(
        project=project,
        version_id=version_id,
        other_version_id=other_version_id,
        activity_id=data["activityId"],
        file_id=data["fileId"],
    )


def test_set_and_remove_data(reviewable: Reviewable):
    response = reviewable.patch({"data": {"overlay": OVERLAY, "other": 1}})
    assert response.status_code in (200, 204), response.text
    assert reviewable.listed()["data"] == {"overlay": OVERLAY, "other": 1}

    # Patch without data keeps it
    response = reviewable.patch({"label": "with overlay"})
    assert response.status_code in (200, 204), response.text
    listed = reviewable.listed()
    assert listed["label"] == "with overlay"
    assert listed["data"] == {"overlay": OVERLAY, "other": 1}

    # Top-level keys are replaced, other keys are kept
    response = reviewable.patch({"data": {"overlay": {"schema": "test/2"}}})
    assert response.status_code in (200, 204), response.text
    assert reviewable.listed()["data"] == {
        "overlay": {"schema": "test/2"},
        "other": 1,
    }

    # Null removes a key
    response = reviewable.patch({"data": {"overlay": None, "other": None}})
    assert response.status_code in (200, 204), response.text
    listed = reviewable.listed()
    assert listed["data"] == {}
    # Server managed data are untouched
    assert listed["filename"] == "review.mp4"
    assert listed["mediaInfo"]


@pytest.mark.parametrize("key", ["filename", "mime", "mediaInfo", "createdFrom"])
def test_reserved_keys(reviewable: Reviewable, key: str):
    response = reviewable.patch({"data": {key: "x", "overlay": OVERLAY}})
    assert response.status_code == 400, response.text
    assert reviewable.listed()["data"] == {}


def test_invalid_label_does_not_change_data(reviewable: Reviewable):
    response = reviewable.patch({"data": {"overlay": OVERLAY}, "label": ""})
    assert response.status_code == 400, response.text
    assert reviewable.listed()["data"] == {}


def test_data_of_other_version(reviewable: Reviewable):
    url = reviewable.url.replace(reviewable.version_id, reviewable.other_version_id)
    response = reviewable.patch({"data": {"overlay": OVERLAY}}, url=url)
    assert response.status_code == 404, response.text
    assert reviewable.listed()["data"] == {}


def test_data_must_be_object(reviewable: Reviewable):
    response = reviewable.patch({"data": [1, 2, 3]})
    assert response.status_code in (400, 422), response.text
