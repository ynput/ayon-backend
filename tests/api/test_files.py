"""Project files (/api/projects/{project}/files)."""

import time
import uuid

import httpx

from .conftest import TempProject


def test_upload_cannot_overwrite_others_file(
    api: httpx.Client,
    other_user: httpx.Client,
    temp_project: TempProject,
) -> None:
    """Uploading with X-File-Id of another user's file is forbidden."""
    url = f"/api/projects/{temp_project.name}/files"
    headers = {"x-file-name": "a.txt", "content-type": "text/plain"}
    response = api.post(url, content=b"original", headers=headers)
    assert response.status_code == 201, response.text
    file_id = response.json()["id"]

    group = f"apitest_{uuid.uuid4().hex[:8]}"
    group_url = f"/api/accessGroups/{group}/_"
    assert api.put(group_url, json={}).status_code == 204
    try:
        other_name = other_user.get("/api/users/me").json()["name"]
        response = api.patch(
            f"/api/users/{other_name}/accessGroups",
            json={
                "accessGroups": [
                    {"project": temp_project.name, "accessGroups": [group]}
                ]
            },
        )
        assert response.status_code == 204, response.text

        # Own uploads work (retried: access groups reload asynchronously)
        for _ in range(20):
            response = other_user.post(url, content=b"mine", headers=headers)
            if response.status_code == 201:
                break
            time.sleep(0.1)
        assert response.status_code == 201, response.text

        response = other_user.post(
            url, content=b"evil", headers={**headers, "x-file-id": file_id}
        )
        assert response.status_code == 403, response.text
        response = api.get(f"{url}/{file_id}")
        if response.is_redirect:
            location = response.headers["location"]
            if location.startswith("/"):  # local storage: payload endpoint
                response = api.get(location)
            else:  # S3 storage: plain client, no API key to S3
                response = httpx.get(location)
        assert response.content == b"original"
    finally:
        api.delete(group_url)
