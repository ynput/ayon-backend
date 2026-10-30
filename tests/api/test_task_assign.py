"""Assigning users to tasks (/api/projects/{project}/tasks/{id}/assign)."""

import time
import uuid
from typing import Any

import httpx

from .conftest import TempProject


def post_until(client: httpx.Client, url: str, json: Any, status: int) -> None:
    """Post until the expected status (access groups reload asynchronously)."""
    response = client.post(url, json=json)
    for _ in range(20):
        if response.status_code == status:
            return
        time.sleep(0.1)
        response = client.post(url, json=json)
    assert response.status_code == status, response.text


def test_assign_follows_update_permissions(
    api: httpx.Client,
    other_user: httpx.Client,
    temp_project: TempProject,
) -> None:
    """The endpoint uses the same rules as updating the task assignees."""
    admin_name = api.get("/api/users/me").json()["name"]
    other_name = other_user.get("/api/users/me").json()["name"]
    folder_id = temp_project.create(
        "folder", name="assign", folderType=temp_project.folder_types[0]
    )
    task_id = temp_project.create(
        "task",
        name="assign",
        taskType=temp_project.task_types[0],
        folderId=folder_id,
        assignees=[admin_name],
    )
    url = f"/api/projects/{temp_project.name}/tasks/{task_id}/assign"
    add_self = {"mode": "add", "users": [other_name]}

    # No access to the project
    post_until(other_user, url, add_self, 403)

    group = f"apitest_{uuid.uuid4().hex[:8]}"
    group_url = f"/api/accessGroups/{group}/_"

    def save_group(fields: list[str]) -> None:
        data = {"attrib_write": {"enabled": True, "fields": fields}}
        response = api.put(group_url, json=data)
        assert response.status_code == 204, response.text

    save_group([])
    try:
        response = api.patch(
            f"/api/users/{other_name}/accessGroups",
            json={
                "accessGroups": [
                    {"project": temp_project.name, "accessGroups": [group]}
                ]
            },
        )
        assert response.status_code == 204, response.text

        # Attribute update is restricted and "assignees" is not whitelisted
        post_until(other_user, url, add_self, 403)
        assert temp_project.get("task", task_id)["assignees"] == [admin_name]

        save_group(["assignees"])
        post_until(other_user, url, add_self, 204)
        assignees = temp_project.get("task", task_id)["assignees"]
        assert sorted(assignees) == sorted([admin_name, other_name])
    finally:
        api.delete(group_url)
