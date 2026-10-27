"""Attributes of entity list items: values of the item over the entity's.

The item fields are tested without the database in
tests/unit/test_entity_list_items.py. These tests cover sorting and
filtering in SQL and saving the items using the REST API.
"""

import json
import uuid
from typing import Any

import httpx
import pytest

from .conftest import GraphQL, TempProject

ITEMS_FIELDS = "edges { id entityId position attrib entityAttrib ownAttrib allAttrib }"


def new_id() -> str:
    return uuid.uuid4().hex


class ListFixture:
    """Folders a, b, c under seq (fps 50) and a list of them.

    entity fps   item fps   attrib fps
    a  24        60         60
    b  30        None       30 (an empty item value doesn't override)
    c  50 (seq)  -          50
    """

    def __init__(self, project: TempProject):
        self.project = project
        folder_type = project.folder_types[0]
        seq = project.create(
            "folder", name="seq", folderType=folder_type, attrib={"fps": 50.0}
        )
        self.folders = {
            "a": project.create(
                "folder",
                name="a",
                folderType=folder_type,
                parentId=seq,
                attrib={"fps": 24.0},
            ),
            "b": project.create(
                "folder",
                name="b",
                folderType=folder_type,
                parentId=seq,
                attrib={"fps": 30.0},
            ),
            "c": project.create(
                "folder", name="c", folderType=folder_type, parentId=seq
            ),
        }
        self.task = project.create(
            "task",
            name="comp",
            taskType=project.task_types[0],
            folderId=self.folders["c"],
        )
        self.item_ids = {name: new_id() for name in self.folders}
        self.list_id = self.create_list(
            "folder",
            [
                (self.item_ids["a"], self.folders["a"], {"fps": 60.0, "listNote": "x"}),
                (self.item_ids["b"], self.folders["b"], {"fps": None}),
                (self.item_ids["c"], self.folders["c"], {}),
            ],
            attributes=["listNote"],
        )

    @property
    def api(self) -> httpx.Client:
        return self.project.api

    def url(self, path: str = "") -> str:
        return f"/api/projects/{self.project.name}/lists{path}"

    def create_list(
        self,
        entity_type: str,
        items: list[tuple[str, str, dict[str, Any]]],
        attributes: list[str] | None = None,
    ) -> str:
        list_id = new_id()
        payload = {
            "id": list_id,
            "label": f"list {list_id[:8]}",
            "entityType": entity_type,
            "items": [
                {"id": item_id, "entityId": entity_id, "attrib": attrib}
                for item_id, entity_id, attrib in items
            ],
        }
        response = self.api.post(self.url(), json=payload)
        assert response.status_code == 201, response.text
        if attributes:
            definitions = [
                {"name": name, "data": {"type": "string", "title": name}}
                for name in attributes
            ]
            url = self.url(f"/{list_id}/attributes")
            response = self.api.put(url, json=definitions)
            assert response.status_code == 200, response.text
        return list_id

    def get_items(self, list_id: str | None = None) -> list[dict[str, Any]]:
        """Items of the list using the REST API (in their order)."""
        response = self.api.get(self.url(f"/{list_id or self.list_id}"))
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        return sorted(items, key=lambda item: item["position"])

    def patch_items(self, items: list[dict[str, Any]]) -> None:
        response = self.api.patch(
            self.url(f"/{self.list_id}/items"),
            json={"mode": "merge", "items": items},
        )
        assert response.status_code == 200, response.text


@pytest.fixture(scope="module")
def lists(temp_project: TempProject) -> ListFixture:
    return ListFixture(temp_project)


def query_items(
    graphql: GraphQL,
    lists: ListFixture,
    list_id: str | None = None,
    sort_by: list[str] | None = None,
    filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    args = []
    if sort_by is not None:
        args.append(f"sortBy: {json.dumps(sort_by)}")
    if filter is not None:
        args.append(f"filter: {json.dumps(json.dumps(filter))}")
    args_str = f"({', '.join(args)})" if args else ""
    data = graphql(
        f'{{ project(name: "{lists.project.name}") {{ '
        f'entityList(id: "{list_id or lists.list_id}") {{ '
        f"items{args_str} {{ {ITEMS_FIELDS} }} }} }} }}"
    )
    return data["project"]["entityList"]["items"]["edges"]


def names(lists: ListFixture, items: list[dict[str, Any]]) -> list[str]:
    by_id = {entity_id: name for name, entity_id in lists.folders.items()}
    return [by_id[item["entityId"]] for item in items]


def fps_filter(key: str, value: float) -> dict[str, Any]:
    return {"conditions": [{"key": f"{key}.fps", "operator": "eq", "value": value}]}


#
# Values
#


def test_item_values(graphql: GraphQL, lists: ListFixture):
    result = query_items(graphql, lists)
    items = dict(zip(names(lists, result), result, strict=True))
    assert items["a"]["attrib"]["fps"] == 60
    assert items["a"]["attrib"]["listNote"] == "x"
    assert items["a"]["entityAttrib"]["fps"] == 24
    assert "listNote" not in items["a"]["entityAttrib"]
    assert sorted(items["a"]["ownAttrib"]) == ["fps", "listNote"]
    assert json.loads(items["a"]["allAttrib"]) == items["a"]["attrib"]

    # An empty item value doesn't override the entity's
    assert items["b"]["attrib"]["fps"] == 30
    assert items["b"]["ownAttrib"] == []

    # Inherited from the parent folder
    assert items["c"]["attrib"]["fps"] == 50
    assert items["c"]["entityAttrib"]["fps"] == 50


def test_list_attributes_of_several_lists(graphql: GraphQL, lists: ListFixture):
    """Each list's items use the attribute config of their own list."""
    entity_id = lists.folders["a"]
    attrib = {"listOne": "1", "listTwo": "2"}
    list1 = lists.create_list(
        "folder", [(new_id(), entity_id, attrib)], attributes=["listOne"]
    )
    list2 = lists.create_list(
        "folder", [(new_id(), entity_id, attrib)], attributes=["listTwo"]
    )
    data = graphql(
        f'{{ project(name: "{lists.project.name}") {{ '
        f'entityLists(ids: ["{list1}", "{list2}"]) {{ edges {{ node {{ id '
        f"items {{ {ITEMS_FIELDS} }} }} }} }} }} }}"
    )
    result = {
        edge["node"]["id"]: edge["node"]["items"]["edges"][0]
        for edge in data["project"]["entityLists"]["edges"]
    }
    assert result[list1]["ownAttrib"] == ["listOne"]
    assert "listTwo" not in result[list1]["attrib"]
    assert result[list2]["ownAttrib"] == ["listTwo"]
    assert "listOne" not in result[list2]["attrib"]


#
# Sorting and filtering
#


@pytest.mark.parametrize(
    "sort_by, expected",
    [
        (["entityAttrib.fps"], ["a", "b", "c"]),
        (["-entityAttrib.fps"], ["c", "b", "a"]),
        (["attrib.fps"], ["b", "c", "a"]),
        (["-attrib.fps"], ["a", "c", "b"]),
    ],
)
def test_sort(graphql: GraphQL, lists: ListFixture, sort_by, expected):
    assert names(lists, query_items(graphql, lists, sort_by=sort_by)) == expected


@pytest.mark.parametrize(
    "key, value, expected",
    [
        ("entityAttrib", 24.0, ["a"]),
        ("entityAttrib", 60.0, []),
        # inherited from the parent folder
        ("entityAttrib", 50.0, ["c"]),
        ("attrib", 60.0, ["a"]),
        ("attrib", 24.0, []),
        # an empty item value doesn't override the entity's
        ("attrib", 30.0, ["b"]),
        ("attrib", 50.0, ["c"]),
    ],
)
def test_filter(graphql: GraphQL, lists: ListFixture, key, value, expected):
    items = query_items(graphql, lists, filter=fps_filter(key, value))
    assert names(lists, items) == expected


def test_task_items(graphql: GraphQL, lists: ListFixture):
    """Tasks inherit the values of their folder"""
    list_id = lists.create_list("task", [(new_id(), lists.task, {"fps": 25.0})])
    [item] = query_items(graphql, lists, list_id=list_id)
    assert item["attrib"]["fps"] == 25
    assert item["entityAttrib"]["fps"] == 50

    items = query_items(
        graphql, lists, list_id=list_id, filter=fps_filter("entityAttrib", 50.0)
    )
    assert [item["entityId"] for item in items] == [lists.task]
    items = query_items(
        graphql, lists, list_id=list_id, filter=fps_filter("entityAttrib", 25.0)
    )
    assert items == []


#
# Saving items (merge)
#


def test_merge_keeps_positions(lists: ListFixture):
    """Items without a position given stay where they are."""
    ids = lists.item_ids
    order = [item["id"] for item in lists.get_items()]
    assert order == [ids["a"], ids["b"], ids["c"]]

    lists.patch_items([{"id": ids["c"], "attrib": {"listNote": "z"}}])
    items = lists.get_items()
    assert [item["id"] for item in items] == order
    assert items[2]["attrib"]["listNote"] == "z"

    # Given positions are used (as when reordering in the Lists page)
    reordered = [ids["c"], ids["a"], ids["b"]]
    lists.patch_items([{"id": id, "position": i} for i, id in enumerate(reordered)])
    assert [item["id"] for item in lists.get_items()] == reordered

    # Restore the order for the other tests
    lists.patch_items([{"id": id, "position": i} for i, id in enumerate(order)])
    assert [item["id"] for item in lists.get_items()] == order


def test_merge_adds_new_items_at_the_end(lists: ListFixture):
    list_id = lists.create_list(
        "folder",
        [(new_id(), lists.folders["a"], {}), (new_id(), lists.folders["b"], {})],
    )
    response = lists.api.patch(
        lists.url(f"/{list_id}/items"),
        json={"mode": "merge", "items": [{"entityId": lists.folders["c"]}]},
    )
    assert response.status_code == 200, response.text
    entity_ids = [item["entityId"] for item in lists.get_items(list_id)]
    assert entity_ids == [lists.folders[name] for name in ("a", "b", "c")]


def test_unchanged_items_are_not_updated(lists: ListFixture):
    ids = lists.item_ids
    before = {item["id"]: item["updatedAt"] for item in lists.get_items()}
    lists.patch_items([{"id": ids["a"], "attrib": {"listNote": "changed"}}])
    after = {item["id"]: item["updatedAt"] for item in lists.get_items()}
    assert after[ids["a"]] != before[ids["a"]]
    assert after[ids["b"]] == before[ids["b"]]
    assert after[ids["c"]] == before[ids["c"]]
