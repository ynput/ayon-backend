"""Fix stored attribute values, which the attribute models reject.

Pydantic 1 implicitly converted some attribute values, which Pydantic 2
rejects (booleans in string attributes, floats in integer attributes).
Entities with such values cannot be loaded. This command finds them
and converts them the same way Pydantic 1 did.

Values, which cannot be converted (for example values violating
a changed attribute constraint), are only reported.
"""

from typing import Any, get_args

from ayon_server.attributes.values import invalid_attrib
from ayon_server.cli import app
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType


def convert_value(value: Any, attr_type: str | None) -> Any:
    """Convert a value the way Pydantic 1 did for the given attribute type"""
    if attr_type == "string" and isinstance(value, bool):
        return str(value)
    if attr_type == "integer" and isinstance(value, float):
        return int(value)
    if attr_type == "list_of_strings" and isinstance(value, list):
        return [str(v) if isinstance(v, bool) else v for v in value]
    if attr_type == "list_of_integers" and isinstance(value, list):
        return [int(v) if isinstance(v, float) else v for v in value]
    return value


async def fix_table(
    table: str,
    key_column: str,
    entity_type: str,
    *,
    dry_run: bool,
    key: str | None = None,
) -> tuple[int, int]:
    """Fix attributes in a table. Return the number of fixed and unfixable values

    When `key` is set, only the row with the given key is checked.
    """

    types = {attr["name"]: attr["type"] for attr in attribute_library[entity_type]}

    updates: list[tuple[str, dict[str, Any]]] = []
    fixed_count = 0
    unfixable_count = 0

    query = f"SELECT {key_column}, attrib FROM {table}"
    args: list[Any] = []
    if key is not None:
        query += f" WHERE {key_column} = $1"
        args.append(key)

    async for row in Postgres.iterate(query, *args):
        attrib = row["attrib"] or {}
        invalid = invalid_attrib(entity_type, attrib)
        if not invalid:
            continue

        row_key = row[key_column]
        fixes = {
            name: convert_value(attrib[name], types.get(name))
            for name in invalid
            if name in attrib
        }
        fixes = {name: v for name, v in fixes.items() if v != attrib[name]}

        # Keep only the fixes, which make the attribute valid
        still_invalid = invalid_attrib(entity_type, {**attrib, **fixes})
        for name, message in still_invalid.items():
            fixes.pop(name, None)
            value = str(attrib.get(name))[:70]
            logger.warning(f"{table} {row_key}: '{name}' = {value}: {message}")
            unfixable_count += 1

        for name, value in fixes.items():
            logger.info(f"{table} {row_key}: '{name}' {attrib[name]!r} -> {value!r}")
        if fixes:
            updates.append((row_key, fixes))
            fixed_count += len(fixes)

    if updates and not dry_run:
        async with Postgres.transaction():
            for row_key, fixes in updates:
                await Postgres.execute(
                    f"UPDATE {table} SET attrib = attrib || $1 WHERE {key_column} = $2",
                    fixes,
                    row_key,
                )

    return fixed_count, unfixable_count


@app.command()
async def fix_attributes(
    project_name: str | None = None,
    dry_run: bool = False,
) -> None:
    """Fix attribute values, which are not valid for their attribute type.

    Without --project-name, all projects and users are checked.
    With --dry-run, the changes are only reported.
    """
    await ayon_init()

    if project_name is None:
        project_names = [project.name for project in await get_project_list()]
    else:
        project_names = [project_name]

    total_fixed = 0
    total_unfixable = 0

    async def fix(
        table: str,
        key_column: str,
        entity_type: str,
        key: str | None = None,
    ) -> int:
        nonlocal total_fixed, total_unfixable
        fixed, unfixable = await fix_table(
            table, key_column, entity_type, dry_run=dry_run, key=key
        )
        total_fixed += fixed
        total_unfixable += unfixable
        return fixed

    if project_name is None:
        await fix("public.users", "name", "user")

    for name in project_names:
        # Project attributes are inherited by the project entities,
        # so they are checked (and rebuilt) together
        fixed = await fix("public.projects", "name", "project", key=name)
        for entity_type in get_args(ProjectLevelEntityType):
            fixed += await fix(f"project_{name}.{entity_type}s", "id", entity_type)

        if fixed and not dry_run:
            await rebuild_inherited_attributes(name)
            await rebuild_hierarchy_cache(name)

    action = "Would fix" if dry_run else "Fixed"
    logger.info(
        f"{action} {total_fixed} attribute values. "
        f"{total_unfixable} values cannot be fixed automatically."
    )
