"""Fix stored attribute values, which are not valid for their definitions.

Attribute values are validated when they are written and trusted when
they are read. When an attribute definition changes (type, constraints,
scope), the stored values may not be valid anymore. This converts them
when possible (the way Pydantic 1 did) and removes the rest.

Runs in the background when attributes are saved, and as `fix-attributes`
CLI command.
"""

from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from ayon_server.entities.core.attrib import attribute_library
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import ProjectLevelEntityType


def invalid_values(model: type[BaseModel], values: dict[str, Any]) -> dict[str, str]:
    """Return {attribute name: error message} of invalid attribute values.

    Attributes without a definition and missing values of required
    attributes are not reported.
    """
    try:
        model.__pydantic_validator__.validate_python(values)
    except ValidationError as e:
        return {
            str(error["loc"][0]): error["msg"]
            for error in e.errors()
            if error["loc"] and str(error["loc"][0]) in values
        }
    return {}


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
) -> int:
    """Fix the attribute values in a table. Return the number of changed values.

    When `key` is set, only the row with the given key is checked.
    When `attribute_names` are set, only these attributes are checked.
    """
    model = get_entity_class(entity_type).model.attrib_model
    types = {attr["name"]: attr["type"] for attr in attribute_library[entity_type]}
    if attribute_names is not None:
        attribute_names = [name for name in attribute_names if name in types]
        if not attribute_names:
            return 0

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
    changed = 0
    remove, convert = "Removed", "Converted"
    if dry_run:
        remove, convert = "Would remove", "Would convert"

    async for row in Postgres.iterate(query, *args):
        attrib = row["attrib"] or {}
        invalid = invalid_values(model, attrib)
        if attribute_names is not None:
            invalid = {k: v for k, v in invalid.items() if k in attribute_names}
        if not invalid:
            continue

        row_key = row[key_column]
        fixes = {name: convert_value(attrib[name], types.get(name)) for name in invalid}
        still_invalid = invalid_values(model, {**attrib, **fixes})
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
        changed += len(invalid)

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

    return changed


async def fix_attribute_values(
    project_name: str | None = None,
    *,
    attribute_names: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    """Fix the stored attribute values. Return the number of changed values.

    Without `project_name`, all projects and users are checked.
    Without `attribute_names`, all attributes are checked.
    With `dry_run`, the changes are only reported.
    """
    if project_name is None:
        project_names = [project.name for project in await get_project_list()]
    else:
        project_names = [project_name]

    kwargs: dict[str, Any] = {"dry_run": dry_run, "attribute_names": attribute_names}
    total = 0

    if project_name is None:
        total += await fix_table("public.users", "name", "user", **kwargs)

    for name in project_names:
        # Project attributes are inherited by the project entities,
        # so they are checked (and rebuilt) together
        changed = await fix_table(
            "public.projects", "name", "project", key=name, **kwargs
        )
        for entity_type in get_args(ProjectLevelEntityType):
            table = f"project_{name}.{entity_type}s"
            changed += await fix_table(table, "id", entity_type, **kwargs)

        if changed and not dry_run:
            await rebuild_inherited_attributes(name)
            await rebuild_hierarchy_cache(name)
        total += changed

    if total:
        logger.info(f"{'Would fix' if dry_run else 'Fixed'} {total} attribute values")
    return total
