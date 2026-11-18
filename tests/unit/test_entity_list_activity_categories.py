"""Activity categories of entity lists (EntityListNode.activity_categories)"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.graphql.nodes.entity_list import entity_list_from_record

NOW = datetime(2026, 1, 1)


def list_record(id: str) -> dict[str, Any]:
    return {
        "id": id,
        "entity_list_type": "generic",
        "entity_list_folder_id": None,
        "entity_type": "version",
        "label": id,
        "access": {},
        "attrib": {},
        "data": {},
        "tags": [],
        "owner": "someone",
        "active": True,
        "created_at": NOW,
        "updated_at": NOW,
        "created_by": "someone",
        "updated_by": "someone",
    }


def test_writable_categories_once_per_request(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def get_accessible_categories(user, *, project, level, **kwargs):
        calls.append(project.name)
        return ["internal", "client"]

    monkeypatch.setattr(
        ActivityCategories, "get_accessible_categories", get_accessible_categories
    )
    user = SimpleNamespace(
        name="artist", is_guest=False, get_guest_access=lambda **kwargs: None
    )
    context = {"user": user, "project": SimpleNamespace(name="test")}

    async def resolve_lists() -> list[list[str]]:
        nodes = [
            await entity_list_from_record("test", list_record(id), context)
            for id in ("a", "b", "c")
        ]
        return [node.activity_categories for node in nodes]

    assert asyncio.run(resolve_lists()) == [["internal", "client"]] * 3
    assert calls == ["test"]
