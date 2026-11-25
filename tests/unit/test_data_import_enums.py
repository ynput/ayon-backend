"""Enum validation of CSV import values"""

import asyncio

import pytest

from api.data_import.import_data import _validate_enum_value
from ayon_server.enum import EnumItem
from ayon_server.exceptions import BadRequestException

ITEMS = [EnumItem(value="main", label="Main")]


def test_tags_not_in_anatomy_are_accepted():
    asyncio.run(_validate_enum_value("custom", ITEMS, None, enum_name="tags"))


def test_closed_enums_reject_unknown_values():
    with pytest.raises(BadRequestException):
        asyncio.run(_validate_enum_value("custom", ITEMS, None, enum_name="statuses"))


def test_new_value_shared_by_rows_is_created_once(monkeypatch):
    created: list[str] = []

    async def create_item(enum_name, item, project_name=None):
        created.append(item.value)

    monkeypatch.setattr(
        "api.data_import.import_data.EnumRegistry.create_item", create_item
    )
    items = list(ITEMS)

    async def validate_rows():
        for _ in range(2):
            await _validate_enum_value(
                "Episode", items, "create", enum_name="folderTypes"
            )

    asyncio.run(validate_rows())
    assert created == ["Episode"]
