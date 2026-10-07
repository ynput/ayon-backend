"""Project-level entities CRUD (operations endpoint).

Entity REST endpoints (create, update, delete) use operations under the hood,
so the operations endpoint covers them. Every module uses its own temporary
project (see `temp_project`).
"""

import struct
import uuid
import zlib
from typing import Any

import pytest

from .conftest import TempProject, operation


def uid() -> str:
    return uuid.uuid4().hex


def name(prefix: str = "e") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def png() -> bytes:
    """A valid 1x1 PNG image."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture(scope="module")
def project(temp_project: TempProject) -> TempProject:
    return temp_project


def folder(project: TempProject, parent_id: str | None = None, **data: Any) -> str:
    return project.create(
        "folder",
        name=data.pop("name", name("folder")),
        folderType=project.folder_types[0],
        parentId=parent_id,
        **data,
    )


def product(project: TempProject, folder_id: str, **data: Any) -> str:
    return project.create(
        "product",
        name=data.pop("name", name("product")),
        folderId=folder_id,
        productType="model",
        **data,
    )


def version(project: TempProject, product_id: str, number: int, **data: Any) -> str:
    return project.create("version", productId=product_id, version=number, **data)


def task(project: TempProject, folder_id: str, **data: Any) -> str:
    return project.create(
        "task",
        name=data.pop("name", name("task")),
        taskType=project.task_types[0],
        folderId=folder_id,
        **data,
    )


def failed(result: dict[str, Any], status: int | None = None) -> bool:
    return not result["success"] and (status is None or result["status"] == status)


#
# Folders
#


class TestFolders:
    def test_create(self, project: TempProject):
        root_name = name("root")
        root = folder(project, name=root_name)
        child = folder(project, root, name="child", label="Child", tags=["a"])

        data = project.get("folder", child)
        assert data["path"] == f"/{root_name}/child"
        assert data["parentId"] == root
        assert data["label"] == "Child"
        assert data["tags"] == ["a"]
        assert data["status"] in project.statuses  # default status
        assert data["active"] is True

    def test_explicit_id(self, project: TempProject):
        folder_id = uid()
        result = project.op(
            "create",
            "folder",
            entity_id=folder_id,
            data={"name": name(), "folderType": project.folder_types[0]},
        )
        assert result["success"] and result["entityId"] == folder_id
        duplicate = project.op(
            "create",
            "folder",
            entity_id=folder_id,
            data={"name": name(), "folderType": project.folder_types[0]},
        )
        assert failed(duplicate, 409)

    def test_sibling_names_are_unique(self, project: TempProject):
        root = folder(project)
        folder(project, root, name="shot")
        for sibling_name in ("shot", "SHOT"):  # case insensitive
            result = project.op(
                "create",
                "folder",
                data={
                    "name": sibling_name,
                    "folderType": project.folder_types[0],
                    "parentId": root,
                },
            )
            assert failed(result, 409), sibling_name
        # the same name is fine elsewhere
        folder(project, folder(project), name="shot")

    def test_root_names_are_unique(self, project: TempProject):
        root_name = name("root")
        folder(project, name=root_name)
        result = project.op(
            "create",
            "folder",
            data={"name": root_name.upper(), "folderType": project.folder_types[0]},
        )
        assert failed(result, 409)

    def test_inactive_siblings_may_share_names(self, project: TempProject):
        root = folder(project)
        folder(project, root, name="old", active=False)
        folder(project, root, name="old")

    def test_invalid_values(self, project: TempProject):
        for data in (
            {"name": "not valid!", "folderType": project.folder_types[0]},
            {"name": name(), "folderType": "UnknownFolderType"},
            {"name": name(), "folderType": project.folder_types[0], "parentId": uid()},
        ):
            result = project.op("create", "folder", data=data)
            assert not result["success"], data
            assert 400 <= result["status"] < 500, result

    def test_folder_cannot_be_its_own_parent(self, project: TempProject):
        folder_id = uid()
        data = {"name": name(), "folderType": project.folder_types[0]}
        result = project.op(
            "create",
            "folder",
            entity_id=folder_id,
            data={**data, "parentId": folder_id},
        )
        assert failed(result, 400)

        folder_id = folder(project)
        result = project.op("update", "folder", folder_id, {"parentId": folder_id})
        assert failed(result, 400)

    def test_folder_cannot_be_moved_under_its_descendant(self, project: TempProject):
        a = folder(project)
        b = folder(project, a)
        c = folder(project, b)
        for target in (b, c):
            result = project.op("update", "folder", a, {"parentId": target})
            assert failed(result, 400), target
            assert "descendants" in result["detail"]
        assert project.get("folder", a).get("parentId") is None

    def test_move_updates_paths(self, project: TempProject):
        a_name, b_name = name("a"), name("b")
        a = folder(project, name=a_name)
        b = folder(project, name=b_name)
        child = folder(project, a, name="child")
        grandchild = folder(project, child, name="grandchild")

        assert project.op("update", "folder", child, {"parentId": b})["success"]
        assert project.get("folder", child)["path"] == f"/{b_name}/child"
        assert (
            project.get("folder", grandchild)["path"] == f"/{b_name}/child/grandchild"
        )

    def test_rename_updates_paths(self, project: TempProject):
        root_name = name("root")
        root = folder(project, name=root_name)
        child = folder(project, root, name="child")
        assert project.op("update", "folder", root, {"name": "renamed_" + root_name})[
            "success"
        ]
        assert project.get("folder", child)["path"] == f"/renamed_{root_name}/child"

    def test_folder_with_versions_is_protected(self, project: TempProject):
        other = folder(project)
        folder_id = folder(project)
        version(project, product(project, folder_id), 1)
        assert project.get("folder", folder_id)["hasVersions"] is True

        changes = (
            {"name": name()},
            {"parentId": other},
            {"folderType": project.folder_types[-1]},
        )
        for change in changes:
            result = project.op("update", "folder", folder_id, change)
            assert failed(result, 403), change
        # other fields can be changed
        assert project.op("update", "folder", folder_id, {"label": "New label"})[
            "success"
        ]
        # force allows the protected changes
        forced = project.op("update", "folder", folder_id, {"name": name()}, force=True)
        assert forced["success"]

    def test_delete(self, project: TempProject):
        root = folder(project)
        child = folder(project, root)
        task_id = task(project, child)
        result = project.op("delete", "folder", root)
        assert result["success"]
        # children are deleted with the folder
        assert not project.exists("folder", child)
        assert not project.exists("task", task_id)

    def test_delete_folder_with_products(self, project: TempProject):
        root = folder(project)
        child = folder(project, root)
        product_id = product(project, child)

        result = project.op("delete", "folder", root)
        assert failed(result, 409)
        assert result["errorCode"] == "delete-folder-with-children"
        assert project.exists("folder", root) and project.exists("product", product_id)

        assert project.op("delete", "folder", root, force=True)["success"]
        assert not project.exists("folder", root)
        assert not project.exists("product", product_id)


#
# Attributes and data
#


class TestAttributes:
    def test_inheritance(self, project: TempProject):
        root = folder(project, attrib={"fps": 30})
        child = folder(project, root)
        task_id = task(project, child)
        for entity_type, entity_id in (("folder", child), ("task", task_id)):
            data = project.get(entity_type, entity_id)
            assert data["attrib"]["fps"] == 30.0, entity_type  # inherited
            assert "fps" not in data["ownAttrib"]

        # a change of the parent is inherited
        assert project.op("update", "folder", root, {"attrib": {"fps": 50}})["success"]
        assert project.get("task", task_id)["attrib"]["fps"] == 50.0

    def test_own_values_are_merged(self, project: TempProject):
        folder_id = folder(project, attrib={"fps": 24, "resolutionWidth": 1920})
        assert project.op(
            "update", "folder", folder_id, {"attrib": {"resolutionHeight": 1080}}
        )["success"]
        data = project.get("folder", folder_id)
        assert data["attrib"]["fps"] == 24.0
        assert data["attrib"]["resolutionWidth"] == 1920
        assert data["attrib"]["resolutionHeight"] == 1080
        assert sorted(data["ownAttrib"]) == [
            "fps",
            "resolutionHeight",
            "resolutionWidth",
        ]

    def test_null_reverts_to_inherited(self, project: TempProject):
        root = folder(project, attrib={"fps": 30})
        child = folder(project, root, attrib={"fps": 24})
        assert project.get("folder", child)["attrib"]["fps"] == 24.0
        assert project.op("update", "folder", child, {"attrib": {"fps": None}})[
            "success"
        ]
        data = project.get("folder", child)
        assert data["attrib"]["fps"] == 30.0
        assert "fps" not in data["ownAttrib"]

    def test_values_are_validated(self, project: TempProject):
        folder_id = folder(project, attrib={"fps": "25"})
        assert project.get("folder", folder_id)["attrib"]["fps"] == 25.0  # converted

        for attrib in ({"fps": "fast"}, {"resolutionWidth": -1}):
            result = project.op("update", "folder", folder_id, {"attrib": attrib})
            assert failed(result, 400), attrib
        assert project.get("folder", folder_id)["attrib"]["fps"] == 25.0

    def test_undefined_attributes_are_dropped(self, project: TempProject):
        folder_id = folder(project, attrib={"notAnAttribute": 1})
        assert "notAnAttribute" not in project.get("folder", folder_id)["attrib"]


class TestData:
    def test_data_is_merged(self, project: TempProject):
        folder_id = folder(project, data={"a": 1, "b": {"c": 2}})
        assert project.op("update", "folder", folder_id, {"data": {"d": 3}})["success"]
        assert project.get("folder", folder_id)["data"] == {
            "a": 1,
            "b": {"c": 2},
            "d": 3,
        }

    def test_null_removes_key(self, project: TempProject):
        folder_id = folder(project, data={"a": 1, "b": 2})
        assert project.op("update", "folder", folder_id, {"data": {"a": None}})[
            "success"
        ]
        assert project.get("folder", folder_id)["data"] == {"b": 2}

    def test_null_data_is_rejected(self, project: TempProject):
        result = project.op(
            "create",
            "folder",
            data={"name": name(), "folderType": project.folder_types[0], "data": None},
        )
        assert failed(result, 400)


class TestThumbnails:
    @pytest.fixture(scope="class")
    def thumbnail_id(self, project: TempProject) -> str:
        response = project.api.post(
            f"/api/projects/{project.name}/thumbnails",
            content=png(),
            headers={"content-type": "image/png"},
        )
        assert response.status_code == 200, response.text
        return response.json()["id"]

    def test_set_thumbnail(self, project: TempProject, thumbnail_id: str):
        folder_id = folder(project, data={"keep": True})
        result = project.op(
            "update", "folder", folder_id, {"thumbnailId": thumbnail_id}
        )
        assert result["success"]
        data = project.get("folder", folder_id)
        assert data["thumbnailId"] == thumbnail_id
        assert data["data"]["keep"] is True  # data is not replaced
        thumbnail_hash = data["data"]["thumbnailHash"]  # bumped

        assert project.op("update", "folder", folder_id, {"thumbnailId": thumbnail_id})[
            "success"
        ]
        assert (
            project.get("folder", folder_id)["data"]["thumbnailHash"] != thumbnail_hash
        )

    def test_unset_thumbnail(self, project: TempProject, thumbnail_id: str):
        folder_id = folder(project, thumbnailId=thumbnail_id)
        assert project.op("update", "folder", folder_id, {"thumbnailId": None})[
            "success"
        ]
        assert project.get("folder", folder_id).get("thumbnailId") is None

    def test_unknown_thumbnail(self, project: TempProject):
        folder_id = folder(project)
        result = project.op("update", "folder", folder_id, {"thumbnailId": uid()})
        assert not result["success"]
        assert project.get("folder", folder_id).get("thumbnailId") is None

    @pytest.mark.parametrize("entity_type", ["task", "version", "workfile"])
    def test_other_entity_types(
        self, project: TempProject, thumbnail_id: str, entity_type: str
    ):
        folder_id = folder(project)
        task_id = task(project, folder_id)
        entity_id = {
            "task": lambda: task_id,
            "version": lambda: version(project, product(project, folder_id), 1),
            "workfile": lambda: project.create(
                "workfile", path=f"/work/{name()}.ma", taskId=task_id
            ),
        }[entity_type]()
        result = project.op(
            "update", entity_type, entity_id, {"thumbnailId": thumbnail_id}
        )
        assert result["success"]
        assert project.get(entity_type, entity_id)["thumbnailId"] == thumbnail_id


#
# Other entity types
#


class TestTasks:
    def test_create_and_update(self, project: TempProject):
        folder_id = folder(project)
        task_id = task(project, folder_id, assignees=["admin"], label="Task")
        data = project.get("task", task_id)
        assert data["folderId"] == folder_id
        assert data["assignees"] == ["admin"]
        assert data["taskType"] == project.task_types[0]

        change = {"assignees": [], "taskType": project.task_types[-1]}
        assert project.op("update", "task", task_id, change)["success"]
        data = project.get("task", task_id)
        assert data["assignees"] == []
        assert data["taskType"] == project.task_types[-1]

    def test_names_are_unique_per_folder(self, project: TempProject):
        folder_id = folder(project)
        task(project, folder_id, name="comp")
        result = project.op(
            "create",
            "task",
            data={
                "name": "Comp",
                "taskType": project.task_types[0],
                "folderId": folder_id,
            },
        )
        assert failed(result, 409)
        task(project, folder(project), name="comp")

    def test_move_to_another_folder(self, project: TempProject):
        target_name = name("target")
        target = folder(project, name=target_name)
        task_id = task(project, folder(project), name="comp")
        assert project.op("update", "task", task_id, {"folderId": target})["success"]
        data = project.get("task", task_id)
        assert data["folderId"] == target
        assert data["path"] == f"/{target_name}/comp"

    def test_unknown_task_type(self, project: TempProject):
        result = project.op(
            "create",
            "task",
            data={
                "name": name(),
                "taskType": "UnknownType",
                "folderId": folder(project),
            },
        )
        assert not result["success"]

    def test_subtasks(self, project: TempProject):
        folder_id = folder(project)
        task_id = task(project, folder_id, data={"subtasks": [{"label": "Block out"}]})
        subtasks = project.get("task", task_id)["data"]["subtasks"]
        assert subtasks[0]["name"] == "block_out"  # created from the label
        assert subtasks[0]["id"]

        duplicate = [{"label": "Block out"}, {"name": "block_out", "label": "Again"}]
        result = project.op(
            "update", "task", task_id, {"data": {"subtasks": duplicate}}
        )
        assert failed(result, 400)


class TestProducts:
    def test_create_and_update(self, project: TempProject):
        folder_id = folder(project)
        product_id = product(project, folder_id, productBaseType="model")
        data = project.get("product", product_id)
        assert data["folderId"] == folder_id
        assert data["productType"] == "model"
        assert data["productBaseType"] == "model"
        assert project.op("update", "product", product_id, {"productType": "look"})[
            "success"
        ]
        assert project.get("product", product_id)["productType"] == "look"

    def test_names_are_unique_per_folder(self, project: TempProject):
        folder_id = folder(project)
        product(project, folder_id, name="modelMain")
        result = project.op(
            "create",
            "product",
            data={"name": "MODELMAIN", "folderId": folder_id, "productType": "model"},
        )
        assert failed(result, 409)

    def test_delete_deletes_versions(self, project: TempProject):
        product_id = product(project, folder(project))
        version_id = version(project, product_id, 1)
        assert project.op("delete", "product", product_id)["success"]
        assert not project.exists("version", version_id)


class TestVersions:
    def test_create(self, project: TempProject):
        folder_id = folder(project)
        task_id = task(project, folder_id)
        product_id = product(project, folder_id)
        version_id = version(project, product_id, 1, taskId=task_id)
        data = project.get("version", version_id)
        assert data["version"] == 1
        assert data["productId"] == product_id
        assert data["taskId"] == task_id
        assert data["author"]  # the user creating the version

    def test_numbers_are_unique_per_product(self, project: TempProject):
        product_id = product(project, folder(project))
        version(project, product_id, 1)
        result = project.op(
            "create", "version", data={"productId": product_id, "version": 1}
        )
        assert failed(result, 409)
        version(project, product_id, 2)
        version(project, product(project, folder(project)), 1)

    def test_hero_version(self, project: TempProject):
        product_id = product(project, folder(project))
        version(project, product_id, 3)
        hero_id = version(project, product_id, -3)
        assert project.get("version", hero_id)["version"] == -3

    def test_deleted_task_is_unlinked(self, project: TempProject):
        folder_id = folder(project)
        task_id = task(project, folder_id)
        version_id = version(project, product(project, folder_id), 1, taskId=task_id)
        assert project.op("delete", "task", task_id)["success"]
        assert project.get("version", version_id).get("taskId") is None


class TestRepresentations:
    @pytest.fixture
    def version_id(self, project: TempProject) -> str:
        return version(project, product(project, folder(project)), 1)

    def test_create(self, project: TempProject, version_id: str):
        files = [{"id": uid(), "path": "/a.ma", "size": 10}]
        representation_id = project.create(
            "representation",
            name="ma",
            versionId=version_id,
            files=files,
            traits={"ayon.2d.Image.v1": {}},
        )
        data = project.get("representation", representation_id)
        assert data["files"][0]["path"] == "/a.ma"
        assert data["traits"] == {"ayon.2d.Image.v1": {}}

    def test_files_are_replaced(self, project: TempProject, version_id: str):
        representation_id = project.create(
            "representation",
            name="ma",
            versionId=version_id,
            files=[{"id": uid(), "path": "/a.ma"}],
        )
        files = [{"id": uid(), "path": "/b.ma"}]
        assert project.op(
            "update", "representation", representation_id, {"files": files}
        )["success"]
        data = project.get("representation", representation_id)
        assert [f["path"] for f in data["files"]] == ["/b.ma"]

    def test_traits_are_merged(self, project: TempProject, version_id: str):
        representation_id = project.create(
            "representation",
            name="ma",
            versionId=version_id,
            traits={"a": {"x": 1}, "b": {}},
        )
        change = {"traits": {"a": None, "c": {"y": 2}}}
        assert project.op("update", "representation", representation_id, change)[
            "success"
        ]
        data = project.get("representation", representation_id)
        assert data["traits"] == {"b": {}, "c": {"y": 2}}

    def test_names_are_unique_per_version(self, project: TempProject, version_id: str):
        project.create("representation", name="ma", versionId=version_id)
        result = project.op(
            "create", "representation", data={"name": "MA", "versionId": version_id}
        )
        assert failed(result, 409)


class TestWorkfiles:
    def test_create(self, project: TempProject):
        task_id = task(project, folder(project))
        path = f"/work/{name()}/scene_v001.ma"
        workfile_id = project.create("workfile", path=path, taskId=task_id)
        data = project.get("workfile", workfile_id)
        assert data["path"] == path
        assert data["taskId"] == task_id
        assert data["createdBy"]

    def test_paths_are_unique(self, project: TempProject):
        path = f"/work/{name()}.ma"
        project.create("workfile", path=path, taskId=task(project, folder(project)))
        result = project.op(
            "create",
            "workfile",
            data={"path": path, "taskId": task(project, folder(project))},
        )
        assert failed(result, 409)


#
# Operations
#


class TestBatches:
    def test_failure_rolls_back_the_batch(self, project: TempProject):
        folder_id = uid()
        result = project.ops(
            operation(
                "create",
                "folder",
                folder_id,
                {"name": name(), "folderType": project.folder_types[0]},
            ),
            operation(
                "create",
                "folder",
                data={"name": "invalid name!", "folderType": project.folder_types[0]},
            ),
        )
        assert not result["success"]
        assert not project.exists("folder", folder_id)

    def test_can_fail_keeps_successful_operations(self, project: TempProject):
        folder_id = uid()
        result = project.ops(
            operation(
                "create",
                "folder",
                folder_id,
                {"name": name(), "folderType": project.folder_types[0]},
            ),
            operation(
                "create",
                "folder",
                data={"name": "invalid name!", "folderType": project.folder_types[0]},
            ),
            canFail=True,
        )
        assert not result["success"]
        assert [op["success"] for op in result["operations"]] == [True, False]
        assert project.exists("folder", folder_id)

    def test_raise_on_error(self, project: TempProject):
        response = project.api.post(
            f"/api/projects/{project.name}/operations",
            json={
                "operations": [
                    operation("update", "folder", uid(), {"label": "x"}),
                ],
                "raiseOnError": True,
            },
        )
        assert response.status_code == 404

    def test_operations_may_depend_on_each_other(self, project: TempProject):
        root, child, task_id = uid(), uid(), uid()
        ft, tt = project.folder_types[0], project.task_types[0]
        result = project.ops(
            operation("create", "folder", root, {"name": name(), "folderType": ft}),
            operation(
                "create",
                "folder",
                child,
                {"name": name(), "folderType": ft, "parentId": root},
            ),
            operation(
                "create",
                "task",
                task_id,
                {"name": name(), "taskType": tt, "folderId": child},
            ),
            operation("update", "folder", root, {"label": "Root"}),
        )
        assert result["success"], result
        assert project.get("task", task_id)["folderId"] == child
        assert project.get("folder", root)["label"] == "Root"

    def test_duplicate_operations_are_rejected(self, project: TempProject):
        folder_id = folder(project)
        response = project.api.post(
            f"/api/projects/{project.name}/operations",
            json={
                "operations": [
                    operation("update", "folder", folder_id, {"label": "a"}),
                    operation("update", "folder", folder_id, {"label": "b"}),
                ]
            },
        )
        assert response.status_code == 400

    def test_missing_entity(self, project: TempProject):
        for op_type in ("update", "delete"):
            result = project.op(op_type, "folder", uid(), {"label": "x"})
            assert failed(result, 404), op_type
