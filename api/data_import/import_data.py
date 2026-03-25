"""
Data import functionality for CSV files.

This module provides endpoints for uploading CSV files and importing
their data into the AYON system as users, folders, tasks, or hierarchies.
"""

import csv
import io
import traceback
from typing import Any, Annotated, List

from fastapi import Path, Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import UserEntity, FolderEntity, TaskEntity
from ayon_server.exceptions import (
    ForbiddenException,
    NotFoundException
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.operations.project_level import ProjectLevelOperations
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import create_uuid

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
    ImportUpload,
    ColumnMapping,
    ImportableColumn,
)
from .router import router


# Redis namespace for storing uploaded CSV files
REDIS_NS = "csv.import"

# Supported MIME types for CSV file uploads
# Maps MIME type to file extension
SUPPORTED_MIME_TYPES = {
    "text/csv": ".csv",
    "application/vnd.ms-excel": ".csv",
    "application/csv": ".csv",
    "text/x-csv": ".csv"
}

# Model classes for each importable entity type
IMPORTABLE_ENTITIES: dict = {
    "user": UserExportImportModel,
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
    "hierarchy": FolderTaskExportImportModel,
}

# Entity classes for each entity type
ENTITY_TYPE_TO_ENTITY_CLASS: dict = {
    "user": UserEntity,
    "folder": FolderEntity,
    "task": TaskEntity,
    "hierarchy": None
}

# Model classes for hierarchy import (folder and task)
HIERARCHY_MODEL_CLASSES: dict = {
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
}

# Entity classes for hierarchy import (folder and task)
HIERARCHY_ENTITY_CLASSES: dict = {
    "folder": FolderEntity,
    "task": TaskEntity,
}

# Sender type for operations status propagation
SENDER_TYPE = "data_import"


@router.put("/import/upload")
async def upload_file(
    user: CurrentUser,
    request: Request,
) -> ImportUpload:
    """Upload a CSV file to Redis for subsequent import operations.

    The uploaded file is stored in Redis with a unique ID that can be
    used in the import endpoint to process the file.

    Args:
        user: Current authenticated user (must be a manager)
        request: HTTP request containing the CSV file

    Returns:
        ImportUpload: Object containing the file ID for use in import

    Raises:
        ForbiddenException: If user is not a manager
        NotFoundException: If file format is not supported
    """
    # Verify user has manager privileges
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    mime = request.headers.get("Content-Type")
    if mime not in SUPPORTED_MIME_TYPES:
        raise NotFoundException("Invalid avatar format")
    csv_bytes = await request.body()
    file_id = create_uuid()
    await Redis.set(REDIS_NS, file_id, csv_bytes, ttl=30*60)

    return ImportUpload(id=file_id)


@router.post("/import/{entity_type}")
async def import_data(
    entity_type: Annotated[
        EntityType, Path(title="Import entity type")],
    user: CurrentUser,
    file_id: str,  # pointer to file stored in Redis
    column_mapping: List[ColumnMapping],
    skip_errors: bool = False,  # what to do if row fails
    existing_strategy: ExistingStrategyType = ExistingItemStrategy.SKIP,  # what to do if item found in target
    project_name: str = None,
    folder_id: str = None,    # limit import to specific folder
    preview: bool  = False,  # do not commit to db if True
) -> ImportStatus:
    """Process CSV file and import users to the database.

    Parses the CSV file and creates/updates users based on the data.
    Expected CSV columns: name, email, full_name, is_admin, etc.
    """
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    file_bytes = await Redis.get(REDIS_NS, file_id)
    if not file_bytes:
        raise ValueError(f"No file {file_id} found.")

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
    required_fields = []

    # For non-hierarchy types, get fields and existing identifiers upfront
    if entity_type != "hierarchy":
        fields = await model_cls.fields(project_name=project_name)
        required_fields = [f.key for f in fields if f.required]
        existing_identifiers = await _get_existing_identifiers(
            model_cls, project_name
        )
    else:
        # For hierarchy, pre-fetch existing identifiers for both folder and task
        for item_type, model_cls in HIERARCHY_MODEL_CLASSES.items():
            fields = await model_cls.fields(project_name=project_name)
            hierarchy_required_fields[item_type] = [
                f.key for f in fields if f.required
            ]
            hierarchy_existing_identifiers[item_type] = await _get_existing_identifiers(
                model_cls, project_name
            )

    operations: ProjectLevelOperations = ProjectLevelOperations(
        project_name,
        user=user,
        sender=f"{SENDER_TYPE}-status-propagation",
        sender_type=SENDER_TYPE,
    )

    originals_and_new = {}
    path_to_ids = {}
    unprocessed = len(rows)
    for row in rows:
        exists = False
        payload = {}

        identifier = None
        item_exists = False
        try:
            if entity_type == "hierarchy":
                item_type = row.get("item_type")
                if item_type not in HIERARCHY_MODEL_CLASSES:
                    error_msg = f"Invalid item_type '{item_type}'"
                    raise ValueError(error_msg)
                model_cls = HIERARCHY_MODEL_CLASSES[item_type]
                entity_cls = HIERARCHY_ENTITY_CLASSES[item_type]
                required_fields = hierarchy_required_fields[item_type]
                existing_identifiers = hierarchy_existing_identifiers[item_type]
            else:
                item_type = entity_type

            has_required = await _has_all_required(required_fields, row, skip_errors)
            if not has_required:
                raise ValueError("Not all required values present")

            path = None
            if "path" in row and row["path"]:
                path = row["path"]
                entity_id = path_to_ids.get(path)
                if not entity_id:
                    # try to resolve from existing items in the database
                    is_task = entity_cls == TaskEntity
                    try:
                        entity_id = await _get_entity_id_by_path(
                            project_name,
                            path,
                            is_task
                        )
                    except NotFoundException:
                        logger.debug(f"Couldn't find entity for '{path}'")

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
                if existing_strategy ==ExistingItemStrategy.UPDATE:
                    exists = True
                else:
                    identifier = path or identifier
                    raise ValueError(f"Item '{identifier}' already exists.")

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

                parent_id = path_to_ids.get(parent_path)
                if parent_id is None:
                    # try to resolve from existing items in the database
                    try:
                        parent_id = await _get_entity_id_by_path(
                            project_name,
                            parent_path,
                            False
                        )
                    except NotFoundException:
                        # Parent path does not exist in the database; proceed without a parent.
                        logger.debug(
                            "Parent path '%s' not found in project '%s' during CSV import; "
                            "continuing without assigning a parent.",
                            parent_path,
                            project_name,
                        )

                if parent_id:
                    path_to_ids[parent_path] = parent_id
                    payload[model_cls.parent_column_name()] = parent_id

                # for tasks
                if folder_id:
                    payload[model_cls.parent_column_name()] = folder_id

                fields = await model_cls.fields(project_name=project_name)
                _create_payload(header, payload, row,fields, column_mapping)

                if  entity_cls != UserEntity:
                    payload["project_name"] = project_name
                logger.info(f"enity_id:: '{entity_id}:{item_type} -> {payload} ")
                if exists:
                    operations.update(
                        item_type,
                        entity_id,
                        **payload
                    )
                    import_status.updated += 1
                else:
                    entity_id = create_uuid()
                    operations.create(
                        item_type,
                        entity_id=entity_id,
                        **payload
                    )
                    import_status.created += 1

                if original_id:
                    originals_and_new[original_id] = entity_id
                if path:
                    path_to_ids[path] = entity_id

                unprocessed -= 1
        except Exception as exp:
            error_msg = f"{exp}"
            import_status.failed_items[row.get("name", "unknown")] = error_msg
            logger.warning(f"{error_msg} - {traceback.format_exc(limit=5)}")
            unprocessed -= 1
            if skip_errors:
                import_status.skipped += 1
                continue
            import_status.failed += 1
            import_status.skipped += unprocessed

            return import_status

    if not preview:
        response = await operations.process()
        if not response.success:
            logger.error(f"Failed to import data", exc_info=True)

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
    header: [str],
    payload: dict[str,str],
    row: dict[str, Any],
    fields: List[ImportableColumn],
    column_mapping: List[ColumnMapping]
) -> None:
    """Prepare the payload with main columns and attributes columns."""
    source_mapping_by_key = {
        mapping.source_key: mapping
        for mapping in column_mapping
    }
    importable_column_by_key = {
        importable_column.key: importable_column
        for importable_column in fields
    }

    for column_name in header:
        mapping = source_mapping_by_key.get(column_name)
        if not mapping:
            continue

        error_handling_mode = mapping.error_handling_mode
        try:
            print(f"mapping::{mapping}")
            value_mapping = {
                value_mapping.source or "dummy" : value_mapping
                for value_mapping in mapping.values_mapping
            }
            print(f"value_mapping::{value_mapping}")
            value = row.get(column_name) or "dummy"
            replacement_mapping = value_mapping.get(value)
            replacement_mapping_action = None
            print(f"replacement_mapping::{replacement_mapping}")
            if replacement_mapping:
                value = replacement_mapping.target
                replacement_mapping_action = replacement_mapping.action

            importable_column = importable_column_by_key.get(column_name)
            if not importable_column:
                logger.debug(f"Unknown column '{column_name}'")
                continue

            print(f"importable_column::{importable_column}")
            if importable_column.enum_items:
                found_enum_item = False
                for enum_item in importable_column.enum_items:
                    if value == enum_item.value:
                        found_enum_item = True
                        break

                if not found_enum_item:
                    if replacement_mapping_action == "create":
                        raise NotImplementedError(
                            "Creation of new enum items not yet implemented"
                        )
                    else:
                        raise ValueError(
                            f"Import contains not matching enum value '{value}'"
                        )

            if "." in column_name:
                main, key = column_name.split(".", 1)
                if main not in payload:
                    payload[main] = {}
                payload[main][key] = value
                if key.startswith("is"):  # temporary hack for boolean fields
                    payload[main][key] = _to_bool(value=payload[main][key])
            else:
                payload[column_name] = value
        except Exception as exp:
            row_id = row[list(row.keys())[0]]  # try to describe row
            error_msg = f"Row '{row_id}' failed with '{exp}''"
            print(error_msg)
            if error_handling_mode != "skip":
                raise ValueError(error_msg)


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