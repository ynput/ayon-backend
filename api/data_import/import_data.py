"""
Data import functionality for CSV files.

This module provides endpoints for uploading CSV files and importing
their data into the AYON system as users, folders, tasks, or hierarchies.
"""

import csv
import io
import traceback
from datetime import datetime
from typing import Any, Annotated, List
import json

from fastapi import Path, Request, Body

from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import UserEntity, FolderEntity, TaskEntity
from ayon_server.enum.enum_item import EnumItem
from ayon_server.enum.enum_registry import EnumRegistry
from ayon_server.entity_lists.models import EntityListItemModel
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    ImportRowErrorException,
)
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.operations.project_level import ProjectLevelOperations
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.utils import create_uuid
from .common import _get_entity_id_by_path, SENDER_TYPE

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
    EntityListExportImportModel,
    HIERARCHY_UNIFIED_COLUMN,
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
    "entity_list_item": EntityListExportImportModel,
}

# Entity classes for each entity type
ENTITY_TYPE_TO_ENTITY_CLASS: dict = {
    "user": UserEntity,
    "folder": FolderEntity,
    "task": TaskEntity,
    "hierarchy": None,
    "entity_list_item": EntityListItemModel
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


@router.put("/import/upload")
async def upload_file(
    user: CurrentUser,
    request: Request,
    csv: Annotated[str, Body()],
    ttl: int | None = None,
) -> ImportUpload:
    """Upload a CSV file to Redis for subsequent import operations.

    The uploaded file is stored in Redis with a unique ID that can be
    used in the import endpoint to process the file.

    Args:
        user: Current authenticated user (must be a manager)
        request: HTTP request containing the CSV file
        csv: bytes of csv file from body
        ttl: Optional time-to-live in seconds for the uploaded file.
             If not provided, defaults to 30 minutes.

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
        raise BadRequestException("Invalid content type")
    file_id = create_uuid()
    ttl_seconds = ttl if ttl is not None else 30 * 60  # 30 minutes default
    await Redis.set(REDIS_NS, file_id, csv, ttl=ttl_seconds)

    return ImportUpload(id=file_id)


@router.post("/import/{import_type}")
async def import_data(
    import_type: Annotated[
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
    """Process CSV file and import entities to the database.

    Parses the CSV file and creates/updates entities based on the data.
    Supports importing users, folders, tasks, or hierarchies (combined).

    Args:
        import_type: Type of entity to import (user, folder, task, hierarchy)
        user: Current authenticated user (must be a manager)
        file_id: ID of the uploaded CSV file in Redis
        column_mapping: List of column mappings (source -> target)
        skip_errors: Whether to skip rows with errors
        existing_strategy: How to handle existing items (skip, update, fail)
        project_name: Project name for folder/task imports
        folder_id: Limit import to specific folder
        preview: If True, don't commit to database

    Returns:
        ImportStatus: Summary of import results
    """
    if not user.is_manager:
        raise ForbiddenException("You must be a manager")

    file_bytes = await Redis.get(REDIS_NS, file_id)
    if not file_bytes:
        raise ValueError(f"No file {file_id} found.")

    header, rows = _parse_csv_rows(file_bytes)

    import_status = ImportStatus()

    model_cls = IMPORTABLE_ENTITIES[import_type]

    hierarchy_existing_identifiers: dict = {}

    # For non-hierarchy types, get fields and existing identifiers upfront
    fields = await model_cls.fields(project_name=project_name)
    required_fields = [f.key for f in fields if f.required]
    if import_type != "hierarchy":
        existing_identifiers = await _get_existing_identifiers(
            model_cls, project_name
        )
    else:
        # For hierarchy, pre-fetch existing identifiers for both folder and task
        for entity_type, model_cls in HIERARCHY_MODEL_CLASSES.items():
            hierarchy_existing_identifiers[entity_type] = await _get_existing_identifiers(
                model_cls, project_name
            )

    operations: ProjectLevelOperations = ProjectLevelOperations(
        project_name,
        user=user,
        sender=f"{SENDER_TYPE}-csv",
        sender_type=SENDER_TYPE,
    )

    originals_and_new = {}
    path_to_ids = {}
    unprocessed = len(rows)

    for row in rows:
        exists = False
        payload = {}
        identifier = None

        try:
            if import_type == "entity_list_item":
                entity_cls = EntityListItemModel
            elif import_type == "hierarchy":
                entity_type = row.get("entity_type")
                if entity_type not in HIERARCHY_MODEL_CLASSES:
                    error_msg = f"Invalid entity_type '{entity_type}'"
                    raise ValueError(error_msg)
                model_cls = HIERARCHY_MODEL_CLASSES[entity_type]
                entity_cls = HIERARCHY_ENTITY_CLASSES[entity_type]
                existing_identifiers = hierarchy_existing_identifiers[entity_type]
            else:
                entity_cls = get_entity_class(import_type)

            await _check_all_required(required_fields, row)

            path = None
            if "path" in row and row["path"]:
                path = row["path"]

            entity_id = await _resolve_entity_id(
                row=row,
                path_to_ids=path_to_ids,
                existing_identifiers=existing_identifiers,
                model_cls=model_cls,
                entity_cls=entity_cls,
                project_name=project_name,
            )

            if entity_id:
                if existing_strategy == ExistingItemStrategy.UPDATE:
                    exists = True
                else:
                    identifier = path or identifier
                    raise ValueError(f"Item '{identifier}' already exists.")

            original_id = row.get("id")
            parent_id, parent_path = await _resolve_parent_id(
                row=row,
                originals_and_new=originals_and_new,
                existing_identifiers=existing_identifiers,
                path_to_ids=path_to_ids,
                project_name=project_name,
                folder_id=folder_id,
            )
            if parent_id:
                path_to_ids[parent_path] = parent_id
                payload[model_cls.parent_column_name()] = parent_id

            # for tasks
            if folder_id:
                payload[model_cls.parent_column_name()] = folder_id

            fields = await model_cls.fields(project_name=project_name)
            await _create_payload(
                project_name,
                header,
                payload,
                row,
                fields,
                column_mapping
            )

            # Add project_name for non-user entities
            if entity_cls != UserEntity:
                payload["project_name"] = project_name

            logger.debug(f"entity_id:: '{entity_id}:{entity_type} -> {payload} ")

            if exists:
                # mark that model has custom update
                custom_updated = await model_cls.update(
                    user=user, preview=preview, **payload
                )
                if not custom_updated:
                    operations.update(
                        entity_type,
                        entity_id,
                        **payload
                    )
                import_status.updated += 1
            else:
                entity_id = await model_cls.create(
                    user=user, preview=preview, **payload
                )
                if not entity_id:
                    entity_id = create_uuid()
                    operations.create(
                        entity_type,
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
            # ImportRowErrorException always stops processing, regardless of skip_errors
            should_stop = (
                isinstance(exp, ImportRowErrorException) or
                not skip_errors
            )

            if should_stop:
                import_status.failed += 1
                import_status.skipped += unprocessed
                return import_status
            import_status.skipped += 1
            continue

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


def _detect_delimiter(content: str) -> str:
    """Detect if CSV uses comma or semicolon as delimiter.

    Args:
        content: CSV file content as string

    Returns:
        Delimiter character (',' or ';')
    """
    first_line = content.split("\n")[0]
    comma_count = first_line.count(",")
    semicolon_count = first_line.count(";")
    if semicolon_count > comma_count:
        return ";"
    return ","


async def _create_payload(
    project_name: str,
    header: list[str],
    payload: dict[str, Any],
    row: dict[str, Any],
    fields: List[ImportableColumn],
    column_mapping: List[ColumnMapping]
) -> None:
    """Prepare the payload with main columns and attributes columns.

    Args:
        header: CSV column headers
        payload: Dictionary to populate with converted values
        row: CSV row data
        fields: Available importable columns
        column_mapping: User-defined column mappings
    """
    # Create lookup dictionaries for efficient access
    source_mapping_by_key = {
        mapping.source_key: mapping
        for mapping in column_mapping
    }
    importable_column_by_key = {
        importable_column.key: importable_column
        for importable_column in fields
    }

    # Process each CSV column
    for csv_column_name in header:
        mapping = source_mapping_by_key.get(csv_column_name)
        if not mapping or mapping.action == "skip":
            # No mapping defined for this column - skip it
            continue
        column_name = mapping.target_key
        error_handling_mode = mapping.error_handling_mode
        if column_name == HIERARCHY_UNIFIED_COLUMN:
            # Special handling for hierarchy imports where folder and task share a column
            if "entity_type" not in row:
                raise ValueError(
                    f"Missing 'entity_type' for hierarchy import in row: {row}"
                )
            entity_type = row["entity_type"]
            if entity_type not in ("folder", "task"):
                raise ValueError(
                    f"Invalid 'entity_type' value '{entity_type}' for hierarchy import "
                    f"in row: {row}"
                )
            # Adjust column name based on entity type
            column_name = f"{entity_type}_type"

        # Get the target column definition
        importable_column = importable_column_by_key.get(column_name)
        if not importable_column:
            logger.debug(f"Unknown column '{column_name}'")
            continue

        try:
            # Build value mapping dictionary
            value_mapping = {
                (vm.source or ""): vm
                for vm in mapping.values_mapping
            }

            # Get the value from the row
            source_value = row.get(csv_column_name)
            if importable_column.value_type == "list_of_strings":
                json_friendly = source_value.replace("'", '"')
                source_value = json.loads(json_friendly)
            else:
                source_value = [source_value]

            for val in source_value:
                replacement_mapping = value_mapping.get(val)
                replacement_mapping_action = None

                # Apply value replacement if defined
                if replacement_mapping:
                    if replacement_mapping.action == "skip":
                        continue

                    val = replacement_mapping.target
                    replacement_mapping_action = replacement_mapping.action

                target_value = _convert_value(importable_column, val)

                # Validate enum values if applicable
                if importable_column.enum_items:
                    await _validate_enum_value(
                        target_value,
                        importable_column.enum_items,
                        replacement_mapping_action,
                        enum_name=getattr(importable_column, 'enum_name', None),
                        project_name=project_name,
                    )

                # Store the value in payload
                _add_value_to_payload(
                    payload=payload,
                    column_name=column_name,
                    column_type=importable_column.value_type,
                    value=target_value
                )

        except Exception as exp:
            row_id = row.get("name", row.get(list(row.keys())[0], "unknown"))
            error_msg = f"Row '{row_id}' failed: {exp}"
            logger.debug(error_msg)
            if error_handling_mode == "abort":
                raise ImportRowErrorException(error_msg)
            elif error_handling_mode == "default":
                _add_value_to_payload(
                    payload=payload,
                    column_name=column_name,
                    column_type=importable_column.value_type,
                    value=importable_column.default_value
                )
            else:
                raise ValueError(error_msg)


def _convert_value(importable_column: ImportableColumn, value: str) -> any:
    if not value:
        # Return None for typed columns to avoid empty string issues
        if importable_column.value_type not in ("string", None):
            return None

    # Convert value based on column type
    if importable_column.value_type == "datetime":
        value = datetime.fromisoformat(value)
    elif importable_column.value_type == "float":
        value = float(value)
    elif importable_column.value_type == "integer":
        value = int(value)
    elif importable_column.value_type == "boolean":
        value = _to_bool(value)
    return value


async def _validate_enum_value(
    value: str,
    enum_items: list,
    replacement_action: str | None,
    enum_name: str | None = None,
    project_name: str | None = None,
) -> None:
    """Validate that a value matches an allowed enum value.

    Args:
        value: The value to validate
        enum_items: List of allowed enum items
        replacement_action: Action to take if value not found
        enum_name: The enum resolver name (for creating new items)
        project_name: The project name (for creating new items)

    Raises:
        ValueError: If value is not in enum and not handled by 'create' action
        NotImplementedError: If 'create' action is not yet implemented
    """
    valid_values = {item.value for item in enum_items}
    to_check = {value} if isinstance(value, str) else set(value)

    # Identify exactly which values are missing
    missing_values = to_check - valid_values

    if missing_values:
        logger.info(f"Missing enum values: {missing_values} | Action: {replacement_action}")

        if replacement_action == "create":
            if not enum_name:
                raise ValueError(
                    "Cannot create enum items: enum name not provided. "
                    "Ensure the field has an associated enum resolver."
                )

            # Create new enum items
            for missing_value in missing_values:
                new_item = EnumItem(
                    value=missing_value,
                    label=missing_value.replace("_", " ").title(),
                )
                await EnumRegistry.create_item(
                    enum_name,
                    new_item,
                    project_name=project_name,
                )
            return

        raise ValueError(
            f"Import contains invalid enum values: {', '.join(map(str, missing_values))}"
        )


def _add_value_to_payload(
    payload: dict[str, Any],
    column_name: str,
    column_type: str | None,
    value: Any
) -> None:
    """Add a value to the payload dictionary.

    Handles both simple fields and nested fields (attrib.field, data.field).
    Uses column_type to determine if the field should be stored as a list.

    Args:
        payload: The payload dictionary to modify
        column_name: The target column name
        column_type: The type of the column (e.g., "list_of_strings")
        value: The value to store
    """
    is_iterable = column_type in ("list_of_strings", "list")
    is_nested = "." in column_name

    # Get or create the target container
    if is_nested:
        main, key = column_name.split(".", 1)
        if main not in payload:
            payload[main] = {}
        container = payload[main]
        is_bool = key.startswith("is")
    else:
        container = payload
        key = column_name
        is_bool = False

    # Handle boolean fields
    if is_bool:
        container[key] = _to_bool(value)
        return

    # Handle value storage
    existing = container.get(key)

    if is_iterable:
        # For iterable types, always store as list
        if existing is None:
            container[key] = [value]
        elif isinstance(existing, list):
            existing.append(value)
        else:
            container[key] = [existing, value]
    else:
        # For non-iterable types, only wrap in list if key exists
        if existing is None:
            container[key] = value
        else:
            container[key] = [existing, value]


async def _check_all_required(
    required_fields: list[str],
    row: dict[str, Any],
) -> None:
    """Check if the row has all required fields.

    Args:
        required_fields: List of required field names
        row: CSV row data

    Raises:
        ValueError: If a required field is missing and skip_errors=False
    """
    for req_field in required_fields:
        if req_field not in row or not row[req_field]:
            logger.debug(f"Missing {req_field}")
            raise ValueError(
                f"Missing required field '{req_field}' in row: {row}"
            )


async def _get_existing_identifiers(
    model: EntityExportImport,
    project_name: str = None
) -> set[tuple]:
    """Get existing entity identifiers from the database.

    Args:
        model: The entity model class
        project_name: Project name for project-specific tables

    Returns:
        Set of tuples representing unique identifiers
    """
    existing_items = await model.get_all_items(
        field_names=model.unique_fields(),
        project_name=project_name
    )
    existing_identifiers = {
        tuple(item[field] for field in model.unique_fields())
        for item in existing_items
    }
    return existing_identifiers


async def _resolve_entity_id(
    row: dict[str, Any],
    path_to_ids: dict[str, str],
    existing_identifiers: set[tuple],
    model_cls,
    entity_cls,
    project_name: str,
) -> str | None:
    """Resolve the entity ID for a CSV row.

    Checks if the entity already exists by path or unique fields.

    Args:
        row: CSV row data
        path_to_ids: Cache of path -> entity_id mappings
        existing_identifiers: Set of existing unique identifiers
        model_cls: The entity model class
        entity_cls: The entity class
        project_name: Project name

    Returns:
        Entity ID if found, None otherwise
    """
    # Check by path first
    if "path" in row and row["path"]:
        path = row["path"]

        # Check in-memory cache
        entity_id = path_to_ids.get(path)
        if entity_id:
            return entity_id

        # Look up in database
        is_task = entity_cls == TaskEntity
        try:
            entity_id = await _get_entity_id_by_path(
                project_name,
                path,
                is_task
            )
            if entity_id:
                path_to_ids[path] = entity_id  # Cache it
                return entity_id
        except NotFoundException:
            logger.debug(f"Couldn't find entity for path '{path}'")

    # Check by unique fields
    if model_cls.unique_fields():
        identifier = tuple(
            row.get(field) for field in model_cls.unique_fields()
        )
        if identifier in existing_identifiers:
            return identifier  # Return the identifier tuple

    return None


async def _resolve_parent_id(
    row: dict[str, Any],
    originals_and_new: dict[str, str],
    existing_identifiers: set[tuple],
    path_to_ids: dict[str, str],
    project_name: str,
    folder_id: str | None,
) -> tuple[str | None, str | None]:
    """Resolve the parent ID for a CSV row.

    Args:
        row: CSV row data
        originals_and_new: Mapping of original IDs to new IDs
        existing_identifiers: Set of existing identifiers
        path_to_ids: Cache of path -> entity_id mappings
        model_cls: The entity model class
        project_name: Project name
        folder_id: Fixed folder ID for tasks

    Returns:
        Tuple of (parent_id, parent_path)
    """
    # Use fixed folder_id for tasks
    if folder_id:
        return folder_id, None

    parent_id = row.get("parent_id")

    # Try to resolve from current import batch
    if parent_id and parent_id in originals_and_new:
        return originals_and_new[parent_id], None

    # Check if parent exists in database
    if parent_id and parent_id not in existing_identifiers:
        return None, None

    # Resolve from path if provided
    if "path" in row and row["path"]:
        path = row["path"]
        path_parts = path.split("/")

        parent_path = (
            "/".join(path_parts[:-1])
            if len(path_parts) > 1
            else ""
        )

        parent_id = path_to_ids.get(parent_path)
        if parent_path and parent_id is None:
            try:
                parent_id = await _get_entity_id_by_path(
                    project_name,
                    parent_path,
                    False  # Not a task
                )
            except NotFoundException:
                raise ValueError(
                    f"Parent path '{parent_path}' not found in "
                    f"project '{project_name}' during CSV import",
                )

        return parent_id, parent_path

    return None, None


def _to_bool(value: Any) -> bool:
    """Convert a value to boolean.

    Args:
        value: Value to convert (bool, str, int, float, or other)

    Returns:
        Boolean representation of the value
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return False
