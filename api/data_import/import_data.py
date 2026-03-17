import csv
import io
from typing import Any, Annotated

import fastapi

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import UserEntity, FolderEntity, TaskEntity
from ayon_server.exceptions import (
    ForbiddenException,
    NotFoundException
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.lib.postgres import Postgres

from .export_data import EntityType
from .models import (
    UserExportImportModel,
    EntityExportImport,
    FolderExportImportModel,
    TaskExportImportModel,
    FolderTaskExportImportModel,
    ExistingItemStrategy,
    ExistingStrategyType,
    ImportStatus,
)
from .router import router


IMPORTABLE_ENTITIES  = {
    "user": UserExportImportModel,
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
    "hierarchy": FolderTaskExportImportModel,
}

ENTITY_TYPE_TO_ENTITY_CLASS: dict = {
    "user": UserEntity,
    "folder": FolderEntity,
    "task": TaskEntity,
    "hierarchy": None
}

HIERARCHY_MODEL_CLASSES: dict = {
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
}

HIERARCHY_ENTITY_CLASSES: dict = {
    "folder": FolderEntity,
    "task": TaskEntity,
}


@router.post("/import/{entity_type}")
async def import_data(
    entity_type: Annotated[
        EntityType, fastapi.Path(title="Import entity type")],
    user: CurrentUser,
    file_bytes: bytes,
    skip_errors: bool = False,
    existing_strategy: ExistingStrategyType = ExistingItemStrategy.SKIP,
    project_name: str = None,
    folder_id: str = None,
) -> int:
) -> ImportStatus:
    """Process CSV file and import users to the database.

    Parses the CSV file and creates/updates users based on the data.
    Expected CSV columns: name, email, full_name, is_admin, etc.
    """
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    header, rows = _parse_csv_rows(file_bytes)

    import_status = ImportStatus()

    try:
        entity_cls = get_entity_class(entity_type)
    except ValueError:
        if entity_type != "hierarchy":
            raise ValueError(f"Unknown entity type: {entity_type}")
    model_cls = IMPORTABLE_ENTITIES[entity_type]

    hierarchy_existing_identifiers: dict = {}
    hierarchy_required_fields: dict = {}

    # For non-hierarchy types, get fields and existing identifiers upfront
    if entity_type != "hierarchy":
        fields = model_cls.fields()
        required_fields = [f["name"] for f in fields if f.get("required")]
        existing_identifiers = await _get_existing_identifiers(
            model_cls, project_name
        )
    else:
        # For hierarchy, pre-fetch existing identifiers for both folder and task
        for item_type, model_cls in HIERARCHY_MODEL_CLASSES.items():
            fields = model_cls.fields()
            hierarchy_required_fields[item_type] = [
                f["name"] for f in fields if f.get("required")
            ]
            hierarchy_existing_identifiers[item_type] = await _get_existing_identifiers(
                model_cls, project_name
            )

    originals_and_new = {}
    path_to_ids = {}
    for row in rows:
        exists = False
        payload = {}
        if entity_type == "hierarchy":
            item_type = row.get("item_type")
            if item_type not in HIERARCHY_MODEL_CLASSES:
                if skip_errors:
                    import_status.skipped += 1
                    import_status.failed_items[row.get("name", "unknown")] = f"Invalid item_type '{item_type}'"
                    continue
                raise ValueError(f"Invalid item_type '{item_type}' in row: {row}")
            model_cls = HIERARCHY_MODEL_CLASSES[item_type]
            entity_cls = HIERARCHY_ENTITY_CLASSES[item_type]
            required_fields = hierarchy_required_fields[item_type]
            existing_identifiers = hierarchy_existing_identifiers[item_type]

        has_required = await _has_all_required(required_fields, row, skip_errors)
        if not has_required:
            continue

        identifier = None
        item_exists = False
        if "path" in row and row["path"]:
            path = row["path"]
            entity_id = path_to_ids.get(path)
            if not entity_id:
                # try to resolve from existing items in the database
                is_task = entity_cls == TaskEntity
                entity_id = await _get_entity_id_by_path(
                    project_name,
                    path,
                    is_task
                )
                if entity_id:
                        item_exists = True
                        path_to_ids[path] = entity_id  # cache
            else:
                item_exists = True
        else:
            # assumes that unique ids are main columns (not attrib.* or data.*)
            identifier = tuple(
                row.get(field) for field in model_cls.unique_fields()
            )
            item_exists = identifier in existing_identifiers

        if item_exists:
            if existing_strategy == ExistingItemStrategy.SKIP:
                import_status.skipped += 1
                import_status.failed_items[row.get("name", "unknown")] = "Item already exists"
                continue
            elif existing_strategy == ExistingItemStrategy.FAIL:
                raise ValueError(f"User already exists: {identifier}")
            elif existing_strategy ==ExistingItemStrategy.UPDATE:
                exists = True

        path = None
        original_id = row.get("id")
        parent_id = row.get("parent_id")
        if parent_id and parent_id in originals_and_new:
            row["parent_id"] = originals_and_new[parent_id]
        elif parent_id and parent_id not in existing_identifiers:
            # reset parent_id if it doesn't exist in the current import batch or
            # in the existing items
            row["parent_id"] = None
        elif "path" in row and row["path"]:
            # if path is provided, we can try to resolve parent_id from the path
            path  = row.pop("path")
            path_parts = path.split("/")
            if len(path_parts) > 1:
                parent_path = "/".join(path_parts[:-1])
            else:
                parent_path = ""

            entity_id = path_to_ids.get(parent_path)
            if entity_id is None:
                # try to resolve from existing items in the database
                entity_id = await _get_entity_id_by_path(
                    project_name,
                    parent_path,
                    False
                )

            if entity_id:
                path_to_ids[parent_path] = entity_id
                payload[model_cls.parent_column_name()] = entity_id

        _create_payload(header, payload, row)

        # for tasks
        if folder_id:
            payload[model_cls.parent_column_name()] = folder_id

        try:
            kwargs = {
                "payload": payload,
                "exists": exists
            }
            if  entity_cls != UserEntity:
                kwargs["project_name"] = project_name
            new_entity = entity_cls(**kwargs)
            await new_entity.save()
            if original_id:
                originals_and_new[original_id] = new_entity.id
            if path:
                path_to_ids[path] = new_entity.id
            if exists:
                import_status.updated += 1
            else:
                import_status.created += 1
        except Exception as exp:
            error_msg = f"Error saving entity {identifier}: {exp}"
            if skip_errors:
                import_status.failed += 1
                import_status.failed_items[row.get("name", "unknown")] = error_msg
                continue
            raise exp

    return import_status


def _parse_csv_rows(file_bytes: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse CSV file and return header and rows.

    Args:
        file_bytes: Raw bytes content of the CSV file

    Returns:
        Tuple of (header_fields, list of row dictionaries)
    """
    content = file_bytes.decode("utf-8")
    delimiter = _detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    header = reader.fieldnames or []
    rows = list(reader)
    return header, rows


def _create_payload(
    header: [str], payload: dict[str,str], row: dict[str, Any]
) -> None:
    """Prepare the payload with main columns and attributes columns."""
    for column_name in header:
        value = row.get(column_name)
        value = None if value == "" else value
        if "." in column_name:
            main, key = column_name.split(".", 1)
            if main not in payload:
                payload[main] = {}
            payload[main][key] = value
            if key.startswith("is"):  # temporary hack for boolean fields
                payload[main][key] = _to_bool(value=payload[main][key])
        else:
            payload[column_name] = value


async def _has_all_required(
    required_fields: list[str], row: dict[str, Any], skip_errors: bool
) -> bool:
    """Check if the row has all required fields."""
    for req_field in required_fields:
        if req_field not in row or not row[req_field]:
            if skip_errors:
                return False
            raise ValueError(f"Missing required field '{req_field}' in row: {row}")
    return True


async def _get_existing_identifiers(
    model: EntityExportImport,
    project_name: str = None
) -> set[tuple]:
    existing_items = await model.get_all_items(
        field_names=model.unique_fields(),
        project_name=project_name
    )
    existing_identifiers = set()
    for existing_row in existing_items:
        existing_identifiers.add(
            tuple(
                existing_row[field] for field in model.unique_fields()
            )
        )
    return existing_identifiers


def _to_bool(value: Any) -> bool:
    """Convert a value to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _detect_delimiter(content: str) -> str:
    """Detect if CSV uses comma or semicolon as delimiter."""
    first_line = content.split("\n")[0]
    comma_count = first_line.count(",")
    semicolon_count = first_line.count(";")
    if semicolon_count > comma_count:
        return ";"
    return ","


async def _get_entity_id_by_path(
    project_name: str,
    path: str,
    is_task: bool = False
) -> str:
    """Get folder or task id by its path."""
    folder_path = path
    task_name = None
    if is_task:
        folder_path, task_name = path.rsplit("/", 1)
    query = f"""
        SELECT h.id, h.path 
        FROM project_{project_name}.hierarchy h 
        WHERE h.path = $1 
    """
    ret =  await Postgres.fetchrow(
        query,
        folder_path
    )
    if not ret:
        raise NotFoundException(
            f"Entity with path '{path}' not found in the database"
        )

    if is_task:
        query = f"""
            SELECT id
            FROM project_{project_name}.tasks
            WHERE folder_id = $1 AND name = $2
        """
        ret =  await Postgres.fetchrow(
            query,
            ret["id"],
            task_name
        )
        if not ret:
            raise NotFoundException(
                f"Entity with path '{path}' not found in the database"
            )

    if ret:
        return ret["id"]

    raise NotFoundException(
        f"Entity with path '{path}' not found in the database"
    )