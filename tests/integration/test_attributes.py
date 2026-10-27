"""Attribute definitions stored in the database and the entity models."""

from typing import Any

import pytest

ENTITY_TYPES = [
    "project",
    "user",
    "folder",
    "task",
    "product",
    "version",
    "representation",
    "workfile",
]


def _entity_class(entity_type: str) -> Any:
    import ayon_server.entities as entities

    return getattr(entities, f"{entity_type.capitalize()}Entity")


def test_attribute_library_matches_database(run):
    from ayon_server.entities.core.attrib import attribute_library
    from ayon_server.lib.postgres import Postgres

    rows = run(Postgres.fetch("SELECT name, scope FROM public.attributes"))
    for entity_type in ENTITY_TYPES:
        expected = {row["name"] for row in rows if entity_type in row["scope"]}
        loaded = {attr["name"] for attr in attribute_library[entity_type]}
        assert loaded == expected, entity_type


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_all_attributes_have_model_fields(run, entity_type):
    """The model generator skips attributes it cannot construct"""
    from ayon_server.entities.core.attrib import attribute_library

    attrib_model = _entity_class(entity_type).model.attrib_model
    defined = {attr["name"] for attr in attribute_library[entity_type]}
    assert defined <= set(attrib_model.model_fields)
