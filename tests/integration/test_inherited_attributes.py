"""Rebuilding the exported attributes of a part of the folder tree.

Everything runs in a project schema created in a transaction,
which is rolled back at the end.
"""

from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid

PROJECT = "test_inherited_attributes"

# name -> parent name. Underscore is a wildcard in LIKE: sh_010 matches shX010
TREE = {
    "assets": None,
    "sh_010": None,
    "shX010": None,
    "sh_010/work": "sh_010",
    "shX010/work": "shX010",
    "sh_010/work/deep": "sh_010/work",
}


class Rollback(Exception):
    pass


async def _create_project() -> dict[str, str]:
    """Create the project schema and folders, return folder ids by path."""
    await Postgres.execute(f"CREATE SCHEMA project_{PROJECT}")
    await Postgres.execute(f"SET LOCAL search_path TO project_{PROJECT}")
    with open("schemas/schema.project.sql") as f:
        await Postgres.execute(f.read())
    await Postgres.set_project_schema(PROJECT)
    await Postgres.execute("INSERT INTO folder_types (name) VALUES ('Folder')")
    await Postgres.execute("INSERT INTO statuses (name) VALUES ('Todo')")

    ids = {path: create_uuid() for path in TREE}
    for path, parent in TREE.items():
        await Postgres.execute(
            """
            INSERT INTO folders (id, name, folder_type, parent_id, status)
            VALUES ($1, $2, 'Folder', $3, 'Todo')
            """,
            ids[path],
            path.split("/")[-1],
            ids[parent] if parent else None,
        )
    await Postgres.execute("REFRESH MATERIALIZED VIEW hierarchy")
    return ids


async def _exported() -> dict[str, tuple[str, dict[str, Any], bool]]:
    rows = await Postgres.fetch(
        "SELECT folder_id, path, attrib, active FROM exported_attributes"
    )
    return {
        row["folder_id"]: (row["path"], row["attrib"], row["active"]) for row in rows
    }


async def _subtree_rebuild_matches_full_rebuild() -> None:
    from ayon_server.entities.core import attribute_library
    from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes

    inherited = sorted(attribute_library.inheritable)[0]
    pattr = {inherited: "project"}

    async def check(folder_ids: list[str], what: str) -> None:
        """Compare the partial rebuild with the rebuild from scratch."""
        await rebuild_inherited_attributes(PROJECT, pattr, folder_ids=folder_ids)
        partial = await _exported()
        await Postgres.execute("DELETE FROM exported_attributes")
        await rebuild_inherited_attributes(PROJECT, pattr)
        assert partial == await _exported(), what

    async with Postgres.transaction():
        ids = await _create_project()
        await rebuild_inherited_attributes(PROJECT, pattr)
        exported = await _exported()
        assert len(exported) == len(TREE)
        assert exported[ids["sh_010/work/deep"]] == (
            "sh_010/work/deep",
            {inherited: "project"},
            True,
        )

        # own attributes: the inheritable one is passed to the children,
        # the other one is not
        await Postgres.execute(
            "UPDATE folders SET attrib = $1 WHERE id = $2",
            {inherited: "own", "notInherited": 1},
            ids["sh_010"],
        )
        await check([ids["sh_010"]], "attribute change")
        exported = await _exported()
        assert exported[ids["sh_010"]][1] == {inherited: "own", "notInherited": 1}
        assert exported[ids["sh_010/work/deep"]][1] == {inherited: "own"}
        assert exported[ids["shX010/work"]][1] == {inherited: "project"}

        await Postgres.execute(
            "UPDATE folders SET active = FALSE WHERE id = $1", ids["sh_010/work"]
        )
        await check([ids["sh_010/work"]], "deactivated")
        exported = await _exported()
        assert exported[ids["sh_010/work/deep"]][2] is False
        assert exported[ids["sh_010"]][2] is True

        await Postgres.execute(
            "UPDATE folders SET name = 'renamed' WHERE id = $1", ids["sh_010/work"]
        )
        await check([ids["sh_010/work"]], "renamed")
        assert (await _exported())[ids["sh_010/work/deep"]][0] == "sh_010/renamed/deep"

        # moved under a folder with other values, and to the top level
        await Postgres.execute(
            "UPDATE folders SET parent_id = $1 WHERE id = $2",
            ids["shX010"],
            ids["sh_010/work"],
        )
        await check([ids["sh_010/work"]], "moved")
        exported = await _exported()
        assert exported[ids["sh_010/work/deep"]][:2] == (
            "shX010/renamed/deep",
            {inherited: "project"},
        )
        await Postgres.execute(
            "UPDATE folders SET parent_id = NULL WHERE id = $1", ids["sh_010/work"]
        )
        await check([ids["sh_010/work"]], "moved to the top level")

        # new parent and child in one go (the parent has nothing exported yet),
        # with a folder rebuilt twice (as a root and as a descendant)
        new_parent, new_child = create_uuid(), create_uuid()
        for folder_id, name, parent_id in (
            (new_parent, "new", ids["sh_010"]),
            (new_child, "child", new_parent),
        ):
            await Postgres.execute(
                """
                INSERT INTO folders (id, name, folder_type, parent_id, status)
                VALUES ($1, $2, 'Folder', $3, 'Todo')
                """,
                folder_id,
                name,
                parent_id,
            )
        await check([new_child, new_parent, ids["sh_010"]], "created")
        assert (await _exported())[new_child] == (
            "sh_010/new/child",
            {inherited: "own"},
            True,
        )

        # nothing to rebuild
        before = await _exported()
        await rebuild_inherited_attributes(PROJECT, pattr, folder_ids=[])
        assert before == await _exported()

        raise Rollback()


async def _force_delete_keeps_other_folders() -> None:
    from ayon_server.entities import FolderEntity

    async with Postgres.transaction():
        ids = await _create_project()
        products = {}
        for path in ("sh_010/work/deep", "shX010/work"):
            products[path] = create_uuid()
            await Postgres.execute(
                """
                INSERT INTO products (id, name, folder_id, product_type, status)
                VALUES ($1, 'product', $2, 'model', 'Todo')
                """,
                products[path],
                ids[path],
            )

        folder = FolderEntity(
            PROJECT, {"id": ids["sh_010"], "name": "sh_010", "path": "/sh_010"}
        )
        await folder.delete(force=True)

        res = await Postgres.fetch("SELECT id FROM products")
        assert [row["id"] for row in res] == [products["shX010/work"]]
        res = await Postgres.fetch("SELECT path FROM hierarchy ORDER BY path")
        assert [row["path"] for row in res] == ["assets", "shX010", "shX010/work"]

        raise Rollback()


async def _save_rebuilds_only_when_needed(monkeypatch) -> None:
    from ayon_server.entities import FolderEntity, folder

    # The rebuild runs after the commit. Run it at once: the test rolls back
    async def run_now(hook) -> None:
        await hook()

    async def no_redis(project_name: str) -> None:
        pass

    monkeypatch.setattr(Postgres, "on_commit", run_now)
    monkeypatch.setattr(folder, "invalidate_hierarchy_cache", no_redis)

    marker = {"marker": 1}

    async def exported(folder_id: str) -> tuple[str, dict[str, Any]]:
        row = await Postgres.fetchrow(
            "SELECT path, attrib FROM exported_attributes WHERE folder_id = $1",
            folder_id,
        )
        return row["path"], row["attrib"]

    async with Postgres.transaction():
        ids = await _create_project()
        await Postgres.execute(
            "INSERT INTO public.projects (name, code) VALUES ($1, 'tia')", PROJECT
        )
        await FolderEntity.refresh_views(PROJECT)
        folder_id, child_id = ids["sh_010/work"], ids["sh_010/work/deep"]

        # A wrong record shows whether the folder was rebuilt
        await Postgres.execute("UPDATE exported_attributes SET attrib = $1", marker)

        folder = await FolderEntity.load(PROJECT, folder_id)
        folder.label = "Label"
        folder.status = "Todo"
        await folder.save()
        assert (await exported(folder_id))[1] == marker

        folder = await FolderEntity.load(PROJECT, folder_id)
        folder.name = "renamed"
        await folder.save()
        assert (await exported(folder_id))[1] != marker
        assert (await exported(child_id))[0] == "sh_010/renamed/deep"
        # the rest of the project is left alone
        assert (await exported(ids["sh_010"]))[1] == marker
        assert (await exported(ids["shX010/work"]))[1] == marker

        await Postgres.execute("UPDATE exported_attributes SET attrib = $1", marker)
        folder = await FolderEntity.load(PROJECT, folder_id)
        folder.active = False
        await folder.save()
        assert (await exported(child_id))[1] != marker
        assert (await exported(ids["sh_010"]))[1] == marker

        raise Rollback()


def _rolled_back(run, coro) -> None:
    try:
        run(coro)
    except Rollback:
        return
    raise AssertionError("The test did not finish")


def test_subtree_rebuild_matches_full_rebuild(run) -> None:
    _rolled_back(run, _subtree_rebuild_matches_full_rebuild())


def test_force_delete_keeps_other_folders(run) -> None:
    _rolled_back(run, _force_delete_keeps_other_folders())


def test_save_rebuilds_only_when_needed(run, monkeypatch) -> None:
    _rolled_back(run, _save_rebuilds_only_when_needed(monkeypatch))


def test_operations_refresh_only_changed_folders(run) -> None:
    from ayon_server.operations.project_level import (
        OperationModel,
        OperationResponseModel,
        OperationsResponseModel,
        _folder_refresh_kwargs,
    )

    def refresh_kwargs(*ops: tuple[str, str, dict[str, Any] | None, bool]):
        operations = [
            OperationModel(type=op, entity_type="folder", entity_id=eid, data=data)
            for op, eid, data, _ in ops
        ]
        responses = [
            OperationResponseModel(
                id=operation.id,
                type=operation.type,
                entity_type="folder",
                entity_id=operation.entity_id,
                success=success,
                status=200,
            )
            for operation, (*_, success) in zip(operations, ops)
        ]
        response = OperationsResponseModel(operations=responses, success=True)
        return _folder_refresh_kwargs(operations, response)

    assert refresh_kwargs(
        ("update", "thumb", {"thumbnailId": "x", "status": "Todo"}, True),
        ("update", "failed", {"name": "x"}, False),
    ) == {"refresh_hierarchy": False, "folder_ids": []}

    assert refresh_kwargs(
        ("create", "new", {"name": "new"}, True),
        ("update", "attr", {"attrib": {"fps": 25}}, True),
        ("update", "off", {"active": False}, True),
    ) == {"refresh_hierarchy": False, "folder_ids": ["new", "attr", "off"]}

    assert refresh_kwargs(
        ("update", "moved", {"parentId": None}, True),
        ("delete", "gone", None, True),
    ) == {"refresh_hierarchy": True, "folder_ids": ["moved"]}
