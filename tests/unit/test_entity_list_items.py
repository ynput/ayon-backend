"""Attribute fields of entity list items (EntityListItemEdge)"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from ayon_server.graphql.nodes.entity_list import EntityListItemEdge
from ayon_server.graphql.nodes.folder import FolderNode, folder_from_record
from ayon_server.utils import json_loads

MANAGER: Any = SimpleNamespace(is_guest=False, is_manager=True)
NOW = datetime(2026, 1, 1)
FOLDER_ID = "a" * 32
LIST_ATTRIBUTES = {"note": "string", "due": "datetime"}


def limited_user(attributes: list[str]) -> Any:
    perms = SimpleNamespace(
        attrib_read=SimpleNamespace(enabled=True, attributes=list(attributes))
    )
    return SimpleNamespace(
        is_guest=False, is_manager=False, permissions=lambda _: perms
    )


def folder_record(attrib: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": FOLDER_ID,
        "name": "shot",
        "label": None,
        "active": True,
        "folder_type": "Shot",
        "parent_id": None,
        "thumbnail_id": None,
        "status": "In progress",
        "tags": [],
        "data": {},
        "created_at": NOW,
        "updated_at": NOW,
        "path": "/shot",
        "attrib": attrib,
        "project_attributes": project,
        "inherited_attributes": {},
    }


def make_folder(user: Any = MANAGER) -> FolderNode:
    record = folder_record({"fps": 25}, {"fps": 24, "resolutionWidth": 1920})
    return asyncio.run(folder_from_record("test", record, {"user": user}))


def make_item(
    item_attrib: dict[str, Any],
    *,
    user: Any = MANAGER,
    forbidden: bool = False,
    list_attributes: dict[str, str] = LIST_ATTRIBUTES,
) -> EntityListItemEdge:
    return EntityListItemEdge(
        project_name="test",
        id="i" * 32,
        entity_type="folder",
        entity_id=FOLDER_ID,
        _entity=make_folder(user),
        _forbidden=forbidden,
        _data={},
        _attrib=item_attrib,
        _list_attributes=list_attributes,
        _user=user,
    )


def test_item_values_over_entity_values():
    item = make_item({"fps": 30, "note": "retake"})

    attrib = item.attrib()
    assert attrib["fps"] == 30
    assert attrib["note"] == "retake"
    assert attrib["resolutionWidth"] == 1920  # inherited from the project
    assert json_loads(item.all_attrib()) == attrib

    entity_attrib = item.entity_attrib()
    assert entity_attrib["fps"] == 25
    assert "note" not in entity_attrib
    assert entity_attrib["resolutionWidth"] == 1920

    assert item.own_attrib() == ["fps", "note"]

    # The entity node is not affected by the item's values
    node = item._entity
    assert isinstance(node, FolderNode)
    assert node.attrib()["fps"] == 25
    assert node.own_attrib() == ["fps"]


def test_own_attrib_only_returned_values():
    item = make_item(
        {
            "fps": None,  # empty: the entity's value is used
            "removedColumn": "x",  # no longer a list attribute
            "notAnAttribute": 1,
            "note": "retake",
        }
    )
    assert item.attrib()["fps"] == 25
    assert "removedColumn" not in item.attrib()
    assert item.own_attrib() == ["note"]


def test_datetime_list_attribute():
    item = make_item({"due": "2026-02-03T04:05:06+00:00", "note": "x"})
    assert item.attrib()["due"] == "2026-02-03T04:05:06+00:00"
    assert json_loads(item.all_attrib())["due"] == "2026-02-03T04:05:06+00:00"
    assert item.own_attrib() == ["due", "note"]


def test_list_attributes_of_another_list():
    # "note" is a list attribute of another list, not of this one
    item = make_item({"note": "retake"}, list_attributes={})
    assert "note" not in item.attrib()
    assert item.own_attrib() == []


def test_forbidden_item():
    item = make_item({"fps": 30, "note": "retake"}, forbidden=True)
    assert item.attrib() == {}
    assert item.all_attrib() == "{}"
    assert item.entity_attrib() == {}
    assert item.own_attrib() == []


def test_attribute_read_access():
    user = limited_user(["fps"])
    item = make_item({"fps": 30, "note": "retake"}, user=user)
    assert set(item.attrib()) <= {"fps", "fullName", "avatarUrl"}
    assert item.attrib()["fps"] == 30
    assert item.entity_attrib() == {"fps": 25}
    assert item.own_attrib() == ["fps"]


def test_from_record_uses_the_list_config():
    folder = folder_record({"fps": 25}, {})
    context = {
        "user": MANAGER,
        "entity_type": "folder",
        "folder_from_record": folder_from_record,
        "list_attributes": {
            "list1": {"note": "string"},
            "list2": {"other": "string"},
        },
    }
    record = {
        "id": "i" * 32,
        "entity_id": FOLDER_ID,
        "entity_list_id": "list1",
        "position": 0,
        "label": None,
        "attrib": {"note": "retake", "other": "x"},
        "data": {},
        "tags": [],
        "folder_path": "",
        "created_at": NOW,
        "updated_at": NOW,
        "created_by": None,
        "updated_by": None,
        "cursor": "0",
        **{f"_entity_{k}": v for k, v in folder.items()},
    }
    item = asyncio.run(EntityListItemEdge.from_record("test", record, context))
    assert item.own_attrib() == ["note"]

    record["entity_list_id"] = "list2"
    item = asyncio.run(EntityListItemEdge.from_record("test", record, context))
    assert item.own_attrib() == ["other"]
