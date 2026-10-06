"""SQL CASE expressions used to sort by anatomy order and enum attributes."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from ayon_server.exceptions import BadRequestException
from ayon_server.graphql.resolvers import sorting

NAMES = ["In progress", "it's done"]


def project(**kwargs: list[str]) -> Any:
    return SimpleNamespace(
        **{key: [{"name": name} for name in names] for key, names in kwargs.items()}
    )


def attrib_sort_case(attr: str) -> str:
    return asyncio.run(sorting.get_attrib_sort_case(attr, "tasks.attrib"))


def test_status_names_are_escaped():
    case = sorting.get_status_sort_case(project(statuses=NAMES), "tasks.status")
    assert case == (
        "CASE WHEN tasks.status = 'In progress' THEN 0"
        " WHEN tasks.status = 'it''s done' THEN 1 ELSE 2 END"
    )


def test_task_type_names_are_escaped():
    case = sorting.get_task_types_sort_case(project(task_types=NAMES))
    assert "tasks.task_type = 'it''s done' THEN 1" in case


def test_folder_type_names_are_escaped():
    case = sorting.get_folder_types_sort_case(project(folder_types=NAMES))
    assert "folders.folder_type = 'it''s done' THEN 1" in case


def test_enum_attribute_is_sorted_in_enum_order():
    assert attrib_sort_case("priority") == (
        "CASE WHEN tasks.attrib->>'priority' = 'urgent' THEN 0"
        " WHEN tasks.attrib->>'priority' = 'high' THEN 1"
        " WHEN tasks.attrib->>'priority' = 'normal' THEN 2"
        " WHEN tasks.attrib->>'priority' = 'low' THEN 3 ELSE 4 END"
    )


def test_enum_values_are_escaped(monkeypatch: pytest.MonkeyPatch):
    values = ["a", "x' THEN 0 END; DROP TABLE users; --"]
    attr_data = {"type": "string", "enum": [{"value": v} for v in values]}
    monkeypatch.setattr(sorting.attribute_library, "by_name", lambda name: attr_data)
    assert attrib_sort_case("custom") == (
        "CASE WHEN tasks.attrib->>'custom' = 'a' THEN 0"
        " WHEN tasks.attrib->>'custom' = 'x'' THEN 0 END; DROP TABLE users; --'"
        " THEN 1 ELSE 2 END"
    )


def test_invalid_attribute_name():
    with pytest.raises(BadRequestException):
        attrib_sort_case("foo'")
