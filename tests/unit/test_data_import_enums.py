"""Enum validation of CSV import values"""

import asyncio

import pytest

from api.data_import.import_data import _validate_enum_value
from ayon_server.enum import EnumItem, EnumRegistry
from ayon_server.exceptions import BadRequestException

ITEMS = [EnumItem(value="main", label="Main")]


def test_tags_not_in_anatomy_are_accepted():
    asyncio.run(_validate_enum_value("custom", ITEMS, None, enum_name="tags"))


def test_closed_enums_reject_unknown_values():
    with pytest.raises(BadRequestException):
        asyncio.run(_validate_enum_value("custom", ITEMS, None, enum_name="statuses"))


def _record_created_items(monkeypatch) -> list[str]:
    created: list[str] = []

    async def create_item(enum_name, item, project_name=None, **kwargs):
        created.append(item.value)

    monkeypatch.setattr(EnumRegistry, "create_item", create_item)
    return created


def test_preview_does_not_create_enum_items(monkeypatch):
    created = _record_created_items(monkeypatch)
    asyncio.run(
        _validate_enum_value(
            "custom",
            ITEMS,
            "create",
            enum_name="folderTypes",
            project_name="demo",
            preview=True,
        )
    )
    assert created == []


def test_import_creates_enum_items(monkeypatch):
    created = _record_created_items(monkeypatch)
    asyncio.run(
        _validate_enum_value(
            "custom",
            ITEMS,
            "create",
            enum_name="folderTypes",
            project_name="demo",
        )
    )
    assert created == ["custom"]
