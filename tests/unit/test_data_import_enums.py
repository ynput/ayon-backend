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
