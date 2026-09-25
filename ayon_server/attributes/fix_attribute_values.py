"""Fix stored attribute values, which are not valid for their definitions.

Attribute values are validated when they are written and trusted when
they are read. When an attribute definition changes (type, constraints,
scope), the stored values may not be valid anymore. This converts them
when possible (the way Pydantic 1 did) and removes the rest.

Runs in the background when attributes are saved, and as `fix-attributes`
CLI command.
"""

from dataclasses import dataclass
from typing import Any, get_args

from ayon_server.attributes.values import invalid_attrib
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import log_traceback, logger
from ayon_server.types import ProjectLevelEntityType


@dataclass
class FixResult:
    #: Number of converted values
    fixed: int = 0
    #: Number of removed values (they could not be converted)
    removed: int = 0

    def __iadd__(self, other: "FixResult") -> "FixResult":
        self.fixed += other.fixed
        self.removed += other.removed
        return self

    def __bool__(self) -> bool:
        return bool(self.fixed or self.removed)


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
    dry_run: bool = False,
    key: str | None = None,
    attribute_names: list[str] | None = None,
) -> FixResult:
    """Fix the attribute values in a table.

    When `key` is set, only the row with the given key is checked.
    When `attribute_names` are set, only these attributes are checked.
    """
    types = {attr["name"]: attr["type"] for attr in attribute_library[entity_type]}
    if attribute_names is not None:
        attribute_names = [name for name in attribute_names if name in types]
        if not attribute_names:
            return FixResult()

    conditions: list[str] = []
    args: list[Any] = []
    if key is not None:
        args.append(key)
        conditions.append(f"{key_column} = ${len(args)}")
    if attribute_names is not None:
        args.append(attribute_names)
        conditions.append(f"attrib ?| ${len(args)}")
    query = f"SELECT {key_column}, attrib FROM {table}"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    updates: list[tuple[str, dict[str, Any], list[str]]] = []
    result = FixResult()
    remove, convert = "Removed", "Converted"
    if dry_run:
        remove, convert = "Would remove", "Would convert"

    async for row in Postgres.iterate(query, *args):
        attrib = row["attrib"] or {}
        invalid = invalid_attrib(entity_type, attrib)
        if attribute_names is not None:
            invalid = {k: v for k, v in invalid.items() if k in attribute_names}
        if not invalid:
            continue

        row_key = row[key_column]
        fixes = {name: convert_value(attrib[name], types.get(name)) for name in invalid}
        still_invalid = invalid_attrib(entity_type, {**attrib, **fixes})
        removed = [name for name in invalid if name in still_invalid]
        for name in removed:
            del fixes[name]
            value = str(attrib[name])[:70]
            logger.warning(
                f"{remove} {table} {row_key} attribute '{name}' = {value}: "
                f"{still_invalid[name]}"
            )
        for name, value in fixes.items():
            logger.info(
                f"{convert} {table} {row_key} attribute '{name}' "
                f"{attrib[name]!r} -> {value!r}"
            )

        updates.append((row_key, fixes, removed))
        result.fixed += len(fixes)
        result.removed += len(removed)

    if updates and not dry_run:
        async with Postgres.transaction():
            for row_key, fixes, removed in updates:
                await Postgres.execute(
                    f"""
                    UPDATE {table} SET attrib = (attrib || $1) - $2::text[]
                    WHERE {key_column} = $3
                    """,
                    fixes,
                    removed,
                    row_key,
                )

    return result


async def fix_attribute_values(
    project_name: str | None = None,
    *,
    attribute_names: list[str] | None = None,
    dry_run: bool = False,
) -> FixResult:
    """Fix the stored attribute values.

    Without `project_name`, all projects and users are checked.
    Without `attribute_names`, all attributes are checked.
    With `dry_run`, the changes are only reported.
    """
    if project_name is None:
        project_names = [project.name for project in await get_project_list()]
    else:
        project_names = [project_name]

    kwargs: dict[str, Any] = {"dry_run": dry_run, "attribute_names": attribute_names}
    total = FixResult()

    if project_name is None:
        total += await fix_table("public.users", "name", "user", **kwargs)

    for name in project_names:
        # Project attributes are inherited by the project entities,
        # so they are checked (and rebuilt) together
        result = await fix_table(
            "public.projects", "name", "project", key=name, **kwargs
        )
        for entity_type in get_args(ProjectLevelEntityType):
            table = f"project_{name}.{entity_type}s"
            result += await fix_table(table, "id", entity_type, **kwargs)

        if result and not dry_run:
            await rebuild_inherited_attributes(name)
            await rebuild_hierarchy_cache(name)
        total += result

    if total:
        action = "Would fix" if dry_run else "Fixed"
        logger.info(
            f"{action} attribute values: {total.fixed} converted, "
            f"{total.removed} removed"
        )
    return total


async def fix_changed_attribute_values(attribute_names: list[str]) -> None:
    """Fix values of the attributes, whose definitions changed.

    Executed in the background after the attributes are saved.
    """
    if not attribute_names:
        return
    try:
        await fix_attribute_values(attribute_names=attribute_names)
    except Exception:
        log_traceback(f"Unable to fix values of attributes {attribute_names}")
