"""Keeping the entity_search rows up to date (the sweep and invalidations).

Everything runs in a project schema created in a transaction,
which is rolled back at the end. `now()` is constant in a transaction,
so changed rows get a later `updated_at` explicitly.
"""

from types import SimpleNamespace

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

PROJECT = "test_entity_search"


class Rollback(Exception):
    pass


def _rolled_back(run, coro) -> None:
    try:
        run(coro)
    except Rollback:
        return
    raise AssertionError("The test did not finish")


async def _create_project() -> dict[str, str]:
    """Create sh010 with a task, a product and versions 1 and 1000."""
    await Postgres.execute(f"CREATE SCHEMA project_{PROJECT}")
    await Postgres.execute(f"SET LOCAL search_path TO project_{PROJECT}")
    with open("schemas/schema.project.sql") as f:
        await Postgres.execute(f.read())
    await Postgres.set_project_schema(PROJECT)
    await Postgres.execute("INSERT INTO folder_types (name) VALUES ('Shot')")
    await Postgres.execute("INSERT INTO task_types (name) VALUES ('Lighting')")
    await Postgres.execute("INSERT INTO statuses (name) VALUES ('Todo')")

    ids = {name: create_uuid() for name in ("sh010", "task", "product", "v1", "v1000")}
    await Postgres.execute(
        "INSERT INTO folders (id, name, folder_type, status)"
        " VALUES ($1, 'sh010', 'Shot', 'Todo')",
        ids["sh010"],
    )
    await Postgres.execute(
        "INSERT INTO tasks (id, name, folder_id, task_type, status)"
        " VALUES ($1, 'light', $2, 'Lighting', 'Todo')",
        ids["task"],
        ids["sh010"],
    )
    await Postgres.execute(
        "INSERT INTO products (id, name, folder_id, product_type, status)"
        " VALUES ($1, 'renderMain', $2, 'render', 'Todo')",
        ids["product"],
        ids["sh010"],
    )
    for key, version in (("v1", 1), ("v1000", 1000)):
        await Postgres.execute(
            "INSERT INTO versions (id, version, product_id, status)"
            " VALUES ($1, $2, $3, 'Todo')",
            ids[key],
            version,
            ids["product"],
        )
    await Postgres.execute("REFRESH MATERIALIZED VIEW hierarchy")
    return ids


async def _literals(entity_id: str) -> str | None:
    row = await Postgres.fetchrow(
        "SELECT literals, updated_at FROM entity_search WHERE entity_id = $1",
        entity_id,
    )
    return row["literals"] if row["updated_at"] else None  # None: outdated


async def _sweep_follows_changes(monkeypatch) -> None:
    from ayon_server.entities.project_aux_tables import aux_table_update
    from ayon_server.entity_search import backfill, mark_attributes_outdated
    from ayon_server.entity_search.indexer import indexed_attributes
    from ayon_server.helpers import project_list

    async with Postgres.transaction():
        ids = await _create_project()
        counts = await backfill(PROJECT)
        assert counts == {
            "folder": 1,
            "task": 1,
            "product": 1,
            "version": 2,
            "comment": 0,
        }
        # Version numbers are padded to three digits, never truncated
        assert await _literals(ids["v1"]) == "rendermain v001"
        assert await _literals(ids["v1000"]) == "rendermain v1000"

        # A product renamed without the indexer queue: the sweep takes
        # its versions along (they did not change themselves)
        await Postgres.execute(
            "UPDATE products SET name = 'renderFinal',"
            " updated_at = updated_at + interval '1 second' WHERE id = $1",
            ids["product"],
        )
        await backfill(PROJECT)
        assert await _literals(ids["v1"]) == "renderfinal v001"

        # Task types are renamed by a cascade, without updated_at
        await aux_table_update(
            PROJECT,
            "task_types",
            [{"name": "Relighting", "original_name": "Lighting"}],
        )
        assert await _literals(ids["task"]) is None
        await backfill(PROJECT)
        assert await _literals(ids["task"]) == "light relighting"

        # A change of the searchable attributes marks the rows of the type
        before = indexed_attributes()
        before["folder"] = [*before["folder"], "removedAttribute"]
        monkeypatch.setattr(
            project_list,
            "get_project_list",
            _async_value([SimpleNamespace(name=PROJECT)]),
        )
        await mark_attributes_outdated(before)
        assert await _literals(ids["sh010"]) is None
        assert await _literals(ids["task"]) is not None
        assert (await backfill(PROJECT))["folder"] == 1

        raise Rollback()


async def _repaired_values_are_reindexed() -> None:
    from ayon_server.attributes.fix_attribute_values import fix_table
    from ayon_server.entities.core.attrib import attribute_library
    from ayon_server.entity_search import backfill, indexed_attributes

    # A free-text attribute without constraints: True is converted, not removed
    names = [
        attr["name"]
        for attr in attribute_library["folder"]
        if attr["name"] in indexed_attributes()["folder"]
        and not {"regex", "min_length", "max_length"} & attr.keys()
    ]
    if not names:
        raise Rollback()  # nothing to test with
    async with Postgres.transaction():
        ids = await _create_project()
        await Postgres.execute(
            "UPDATE folders SET attrib = $1 WHERE id = $2",
            {names[0]: True},  # not a string: converted to "True"
            ids["sh010"],
        )
        await backfill(PROJECT)
        assert await fix_table(f"project_{PROJECT}.folders", "id", "folder") == 1
        assert await _literals(ids["sh010"]) is None
        await backfill(PROJECT)
        row = await Postgres.fetchrow(
            "SELECT attributes FROM entity_search WHERE entity_id = $1", ids["sh010"]
        )
        assert row["attributes"] == "true"
        raise Rollback()


def _async_value(value):
    async def get(*args, **kwargs):
        return value

    return get


def test_sweep_follows_changes(run, monkeypatch) -> None:
    _rolled_back(run, _sweep_follows_changes(monkeypatch))


def test_repaired_values_are_reindexed(run) -> None:
    _rolled_back(run, _repaired_values_are_reindexed())


def test_dynamic_enums_are_not_free_text(run, monkeypatch) -> None:
    from ayon_server.entities.core.attrib import attribute_library
    from ayon_server.entity_search import indexed_attributes

    monkeypatch.setitem(
        attribute_library.data,
        "folder",
        [
            {"name": "code", "type": "string"},
            {"name": "status", "type": "string", "enum_resolver": "statuses"},
            {"name": "kind", "type": "string", "enum": [{"value": "a"}]},
            {"name": "description", "type": "string"},
        ],
    )
    assert indexed_attributes()["folder"] == ["code"]
