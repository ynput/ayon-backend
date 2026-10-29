"""Duplicating entity lists (without the database)"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.entity_lists import duplicate_entity_list as module
from ayon_server.entity_lists.entity_list import EntityList
from ayon_server.entity_lists.models import (
    EntityListItemModel,
    EntityListModel,
    EntityListSummary,
)
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)

PAST = datetime(2020, 1, 1, tzinfo=UTC)
USER: Any = SimpleNamespace(name="alice")


class FakePostgres:
    labels: set[str] = set()
    folders: set[str] = set()

    @classmethod
    async def set_project_schema(cls, project_name: str) -> None:
        pass

    @classmethod
    async def fetch(cls, query: str, base: str) -> list[dict[str, str]]:
        return [{"label": x} for x in cls.labels if x.startswith(base)]

    @classmethod
    async def fetchrow(cls, query: str, value: str) -> dict[str, int] | None:
        used = cls.labels if "FROM entity_lists" in query else cls.folders
        return {"?column?": 1} if value in used else None


def make_source(label: str = "Dailies", **kwargs: Any) -> EntityList:
    items = [
        EntityListItemModel(
            id=f"item{i}",
            entity_id=f"entity{i}",
            position=i,
            label=f"label{i}",
            attrib={"note": str(i)},
            data={"x": i},
            tags=[f"tag{i}"],
            folder_path=f"/seq/shot{i}",
            created_by="bob",
            updated_by="bob",
            created_at=PAST,
            updated_at=PAST,
        )
        for i in (0, 1, 2)
    ]
    values: dict[str, Any] = {
        "id": "source",
        "entity_list_type": "review-session",
        "entity_list_folder_id": "folder1",
        "entity_type": "version",
        "label": label,
        "access": {
            "alice": 10,
            "!team": 20,
            "^group": 30,
            "__guests__": 10,
            "guest:john@example.com": 10,
        },
        "attrib": {"description": "desc"},
        "data": {
            "attributes": [{"name": "note"}],
            "publicLinks": [{"id": "link"}],
            "guestActivityCategories": {"john@example.com": "review"},
            "count": 3,
        },
        "template": {"name": "{x}"},
        "tags": ["a", "b"],
        "items": items,
        "owner": "bob",
        "created_by": "bob",
        "updated_by": "bob",
        "created_at": PAST,
        "updated_at": PAST,
        "active": False,
    }
    values.update(kwargs)
    return EntityList("test", EntityListModel(**values))


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[EntityListModel]:
    FakePostgres.labels = set()
    FakePostgres.folders = {"folder1", "folder2"}
    monkeypatch.setattr(module, "Postgres", FakePostgres)

    payloads: list[EntityListModel] = []

    async def save(self: EntityList, **kwargs: Any) -> EntityListSummary:
        payloads.append(self.payload)
        return EntityListSummary(
            id=self.id,
            entity_list_type=self.entity_list_type,
            entity_type=self.entity_type,
            label=self.payload.label,
            count=len(self.items),
        )

    monkeypatch.setattr(EntityList, "save", save)
    return payloads


def duplicate(source: EntityList, **kwargs: Any) -> EntityListSummary:
    return asyncio.run(module.duplicate_entity_list("test", source, USER, **kwargs))


def test_copies_content(saved: list[EntityListModel]) -> None:
    source = make_source()
    summary = duplicate(source)
    [copy] = saved
    src = source.payload

    assert summary.id == copy.id != src.id
    assert summary.count == 3
    assert copy.label == "Dailies (copy)"
    for key in (
        "entity_type",
        "entity_list_type",
        "entity_list_folder_id",
        "attrib",
        "template",
        "tags",
    ):
        assert getattr(copy, key) == getattr(src, key), key
    assert copy.data["attributes"] == [{"name": "note"}]
    assert copy.access["alice"] == 10
    assert copy.access["!team"] == 20
    assert copy.access["^group"] == 30


def test_copies_items_in_order(saved: list[EntityListModel]) -> None:
    source = make_source()
    duplicate(source)
    [copy] = saved

    assert [i.position for i in copy.items] == [0, 1, 2]
    assert not {i.id for i in copy.items} & {i.id for i in source.items}
    for new, old in zip(copy.items, source.items, strict=True):
        for key in ("entity_id", "label", "attrib", "data", "tags", "folder_path"):
            assert getattr(new, key) == getattr(old, key), key
        assert new.created_by == "alice"
        assert new.created_at > PAST
    assert copy.items[0].attrib is not source.items[0].attrib


def test_drops_private_data(saved: list[EntityListModel]) -> None:
    source = make_source()
    duplicate(source)
    [copy] = saved

    assert set(copy.access) == {"alice", "!team", "^group"}
    assert "publicLinks" not in copy.data
    assert "guestActivityCategories" not in copy.data
    assert copy.owner == copy.created_by == copy.updated_by == "alice"
    assert copy.created_at > PAST
    assert copy.active is True

    # the source is untouched
    assert "__guests__" in source.payload.access
    assert "publicLinks" in source.payload.data
    assert source.payload.owner == "bob"
    assert source.payload.active is False


def test_free_label(saved: list[EntityListModel]) -> None:
    source = make_source()
    FakePostgres.labels = {"Dailies", "Dailies (copy)", "Dailies (copy 3)"}
    assert duplicate(source).label == "Dailies (copy 2)"
    FakePostgres.labels.add("Dailies (copy 2)")
    assert duplicate(source).label == "Dailies (copy 4)"


def test_explicit_label(saved: list[EntityListModel]) -> None:
    source = make_source()
    assert duplicate(source, label="  Mine ").label == "Mine"

    FakePostgres.labels = {"Taken"}
    with pytest.raises(ConflictException):
        duplicate(source, label="Taken")
    with pytest.raises(BadRequestException):
        duplicate(source, label=" ")


def test_folder(saved: list[EntityListModel]) -> None:
    source = make_source()
    duplicate(source)
    duplicate(source, entity_list_folder_id="folder2", use_source_folder=False)
    duplicate(source, entity_list_folder_id=None, use_source_folder=False)
    assert [c.entity_list_folder_id for c in saved] == ["folder1", "folder2", None]

    with pytest.raises(NotFoundException):
        duplicate(source, entity_list_folder_id="missing", use_source_folder=False)


def test_empty_list(saved: list[EntityListModel]) -> None:
    summary = duplicate(make_source(items=[]))
    assert summary.count == 0
    assert saved[0].items == []
