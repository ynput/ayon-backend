"""
Data import functionality for CSV files.

This module provides endpoints for uploading CSV files and importing
their data into the AYON system as users, folders, tasks, or hierarchies.
"""

import csv
import io
import re
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import Body, Query, Request

from ayon_server.activities import create_activity
from ayon_server.activities.activity_categories import ActivityCategories
from ayon_server.activities.utils import MAX_BODY_LENGTH
from ayon_server.api.dependencies import CurrentUser
from ayon_server.entities import FolderEntity, ProjectEntity, TaskEntity, UserEntity
from ayon_server.entity_lists import EntityList
from ayon_server.entity_lists.models import EntityListItemModel
from ayon_server.enum.enum_item import EnumItem
from ayon_server.enum.enum_registry import EnumRegistry
from ayon_server.events.eventstream import EventStream
from ayon_server.exceptions import (
    BadRequestException,
    ForbiddenException,
    ImportRowErrorException,
    NotFoundException,
)
from ayon_server.helpers.entity_access import EntityAccessHelper
from ayon_server.helpers.get_entity_class import get_entity_class
from ayon_server.helpers.project_list import normalize_project_name
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.operations.project_level import (
    OperationsProgress,
    ProjectLevelOperations,
)
from ayon_server.types import ProjectLevelEntityType
from ayon_server.utils import create_uuid

from .common import (
    SENDER_TYPE,
    ImportEntityType,
    ProjectNameQuery,
    RowSkippedException,
    get_entity_id_by_path,
)
from .models import (
    COMMENT_CATEGORY_COLUMN,
    COMMENT_COLUMN,
    HIERARCHY_UNIFIED_COLUMN,
    ColumnMapping,
    ColumnValueMapping,
    DuplicateItemStrategy,
    EntityExportImport,
    EntityListExportImportModel,
    EntityListItemsImport,
    ExistingItemStrategy,
    FolderExportImportModel,
    FolderTaskExportImportModel,
    ImportableColumn,
    ImportStatus,
    ImportUpload,
    MissingItemStrategy,
    TaskExportImportModel,
    UserExportImportModel,
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
    "text/x-csv": ".csv",
}

# Model classes for each importable entity type
IMPORTABLE_ENTITIES: dict[str, Any] = {
    "user": UserExportImportModel,
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
    "hierarchy": FolderTaskExportImportModel,
    "entity_list_item": EntityListExportImportModel,
}

# Entity classes for each entity type
ENTITY_TYPE_TO_ENTITY_CLASS: dict[str, Any] = {
    "user": UserEntity,
    "folder": FolderEntity,
    "task": TaskEntity,
    "hierarchy": None,
    "entity_list_item": EntityListItemModel,
}

# Model classes for hierarchy import (folder and task)
HIERARCHY_MODEL_CLASSES: dict[str, Any] = {
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
}

# Entity classes for hierarchy import (folder and task)
HIERARCHY_ENTITY_CLASSES: dict[str, Any] = {
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

    mime = request.headers.get("Content-Type")
    if mime not in SUPPORTED_MIME_TYPES:
        raise BadRequestException("Invalid content type")
    file_id = create_uuid()
    ttl_seconds = ttl if ttl is not None else 30 * 60  # 30 minutes default
    ttl_seconds = min(ttl_seconds, 86400)  # Cap at 24 hours
    await Redis.set(REDIS_NS, file_id, csv, ttl=ttl_seconds)

    return ImportUpload(id=file_id)


@router.post("/import/{import_type}")
async def import_data(
    import_type: ImportEntityType,
    user: CurrentUser,
    file_id: str,  # pointer to file stored in Redis
    column_mapping: list[ColumnMapping],
    existing_strategy: ExistingItemStrategy = ExistingItemStrategy.UPDATE,
    missing_strategy: MissingItemStrategy = MissingItemStrategy.CREATE,
    duplicate_strategy: DuplicateItemStrategy = DuplicateItemStrategy.SKIP,
    rows_entity_type: Annotated[
        Literal["folder", "task"] | None,
        Query(alias="entity_type"),
    ] = None,
    new_list_label: str | None = None,
    new_list_entity_type: ProjectLevelEntityType | None = None,
    project_name: ProjectNameQuery = None,
    folder_id: str | None = None,  # limit import to specific folder
    preview: bool = False,  # do not commit to db if True
) -> ImportStatus:
    """Process CSV file and import entities to the database.

    Parses the CSV file and creates/updates entities based on the data.
    Supports importing users, folders, tasks, or hierarchies (combined).

    Args:
        import_type: Type of entity to import (user, folder, task, hierarchy)
        user: Current authenticated user (must be a manager)
        file_id: ID of the uploaded CSV file in Redis
        column_mapping: List of column mappings (source -> target)
        existing_strategy: How to handle existing items (skip, update, fail)
        missing_strategy: How to handle rows matching no existing item
            (create, skip). With skip, folders and tasks are matched by path,
            or by name when there is no path, and entity type is optional.
        duplicate_strategy: With missing_strategy skip, what to do when a name
            matches several folders or tasks (skip the row, update all of them)
        rows_entity_type: For hierarchy imports, every row is a folder or a task
            and no entity type column is needed
        new_list_label: For list items, create a new list with this label and
            import into it (with new_list_entity_type) instead of folder_id
        project_name: Project name for folder/task imports
        folder_id: Limit import to specific folder
        preview: If True, don't commit to database

    Returns:
        ImportStatus: Summary of import results
    """

    if import_type == "user" and not user.is_admin:
        raise ForbiddenException("You must be an admin to import users")

    if project_name is not None:
        project_name = await normalize_project_name(project_name)

        if not user.is_manager:
            permissions = user.permissions(project_name=project_name)
            # If either create or attrib_write permission check is enabled,
            # raise ForbiddenException to prevent import. User has to have
            # full write access to the hierarchy in order to import data.
            if permissions.create.enabled or permissions.attrib_write.enabled:
                raise ForbiddenException("Insufficient permissions to import data")

    elif not user.is_manager:
        # This technically should not happen as project_name is required
        # for folder/task imports, but we check anyway
        raise ForbiddenException("You must be a manager to import data")

    update_only = missing_strategy == MissingItemStrategy.SKIP
    update_all_duplicates = duplicate_strategy == DuplicateItemStrategy.ALL

    file_bytes = await Redis.get(REDIS_NS, file_id)
    if not file_bytes:
        raise BadRequestException(f"No file {file_id} found.")

    header, rows = _parse_csv_rows(file_bytes)

    import_status = ImportStatus()

    # Filter out empty rows
    filtered_rows = [row for row in rows if not _is_row_empty(row)]
    total_rows = len(filtered_rows)

    main_phase_label = "validation" if preview else "import"
    status_str = "successfully"
    # Send start event
    event_id = await EventStream.dispatch(
        "import.data",
        project=project_name,
        description=f"Starting {main_phase_label} of {total_rows} rows",
        summary={"total": total_rows, "type": import_type},
        finished=False,
        store=True,
    )

    model_cls = IMPORTABLE_ENTITIES[import_type]

    hierarchy_existing_identifiers: dict[str, set[tuple[str, ...]]] = {}

    # For non-hierarchy types, get fields and existing identifiers upfront
    fields = await model_cls.fields(project_name=project_name, parent_id=folder_id)
    # required fields are needed to create entities, updates only need a match
    required_fields = [] if update_only else [f.key for f in fields if f.required]
    if rows_entity_type:
        required_fields = [key for key in required_fields if key != "entity_type"]
    existing_identifiers: set[tuple[str, ...]] = set()
    list_items: EntityListItemsImport | None = None
    new_list: EntityList | None = None
    if import_type == "entity_list_item":
        if not project_name:
            raise BadRequestException("Project name is required to import list items")
        list_items = EntityListItemsImport(project_name, user)
        if new_list_label:
            if folder_id:
                raise BadRequestException("Import into a list or a new list, not both")
            if not new_list_entity_type:
                raise BadRequestException("The new list needs an entity type")
            if update_only:
                raise BadRequestException("A new list can only get new items")
            new_list = await list_items.create_list(
                new_list_label.strip(), new_list_entity_type
            )
    elif import_type != "hierarchy":
        existing_identifiers = await _get_existing_identifiers(model_cls, project_name)
    else:
        # For hierarchy, pre-fetch existing identifiers for both folder and task
        for hier_entity_type, model_cls in HIERARCHY_MODEL_CLASSES.items():
            hierarchy_existing_identifiers[
                hier_entity_type
            ] = await _get_existing_identifiers(model_cls, project_name)

    operations: ProjectLevelOperations | None = None
    if project_name:
        operations = ProjectLevelOperations(
            project_name,
            user=user,
        )

    originals_and_new: dict[str, Any] = {}
    path_to_ids: dict[str, Any] = {}
    existing_hierarchy = _ExistingHierarchy(project_name)
    comment_checker = _CommentChecker(project_name, user)
    # updates are merged per entity, operations reject two updates of one entity
    pending_updates: dict[tuple[str, str], dict[str, Any]] = {}
    pending_comments: list[tuple[str, str, str, str | None]] = []
    queued_creates = 0
    unprocessed = len(filtered_rows)
    row_number = 0

    task_type_enum_items = await EnumRegistry.resolve(
        "taskTypes", project_name=project_name
    )
    if not task_type_enum_items:
        raise BadRequestException("No task types")
    default_task_type = task_type_enum_items[0].value

    fields_cache: dict[type, list[ImportableColumn]] = {}

    # Pre-build lookups for _get_entity_type (called per-row in hierarchy imports)
    initial_model_cls = IMPORTABLE_ENTITIES[import_type]
    if initial_model_cls not in fields_cache:
        fields_cache[initial_model_cls] = await initial_model_cls.fields(
            project_name=project_name, parent_id=folder_id
        )
    initial_fields = fields_cache[initial_model_cls]
    entity_type_importable_column_by_key = {ic.key: ic for ic in initial_fields}
    entity_type_value_mapping_by_key = {
        mapping.target_key: {(vm.source or ""): vm for vm in mapping.values_mapping}
        for mapping in column_mapping
        if mapping.action != "skip"
    }

    for row in filtered_rows:
        row_number += 1

        current_progress, trigger_update = _trigger_status_update(
            row_number, total_rows
        )

        if trigger_update:
            await EventStream.update(
                event_id,
                project=project_name,
                description=f"Validating row: {row_number} of {total_rows} rows",
                progress=current_progress,
                summary=await _prepare_status_summary(import_status),
                status="in_progress",
                store=False,
            )

        import_entity_data: dict[str, Any] = {}
        identifier = None
        path = None
        entity_type: str = import_type  # Initialize for non-hierarchy types
        matched_ids: list[str] = []
        try:
            if import_type == "entity_list_item":
                entity_cls: type[Any] = EntityListItemModel
            elif import_type == "hierarchy":
                row_entity_type = rows_entity_type or await _get_entity_type(
                    project_name,
                    row,
                    column_mapping,
                    entity_type_importable_column_by_key,
                    entity_type_value_mapping_by_key,
                    required=not update_only,
                )
                if row_entity_type:
                    entity_type = row_entity_type
                else:
                    # update-only rows may leave out the entity type,
                    # it comes from the folder or task they match
                    match_path, match_name = await _get_match_keys(
                        project_name,
                        row,
                        column_mapping,
                        entity_type_importable_column_by_key,
                        entity_type_value_mapping_by_key,
                    )
                    entity_type, matched_ids = await existing_hierarchy.match(
                        None, match_path, match_name, update_all_duplicates
                    )
                if entity_type not in HIERARCHY_MODEL_CLASSES:
                    error_msg = f"Invalid entity_type '{entity_type}'"
                    raise BadRequestException(error_msg)
                model_cls = HIERARCHY_MODEL_CLASSES[entity_type]
                entity_cls = HIERARCHY_ENTITY_CLASSES[entity_type]
                existing_identifiers = hierarchy_existing_identifiers[entity_type]
            else:
                entity_cls = get_entity_class(import_type)

            if model_cls not in fields_cache:
                fields_cache[model_cls] = await model_cls.fields(
                    project_name=project_name
                )
            fields = fields_cache[model_cls]
            await _remap_row(
                project_name,
                header,
                import_entity_data,
                row,
                fields,
                column_mapping,
                entity_type=entity_type if import_type == "hierarchy" else None,
            )
            comment = import_entity_data.pop(COMMENT_COLUMN, None)
            comment_category = import_entity_data.pop(COMMENT_CATEGORY_COLUMN, None)
            if comment:
                comment_category = await comment_checker.check(
                    comment, comment_category
                )
            row_values = dict(import_entity_data)

            if list_items is not None:
                entity_list = new_list or await list_items.get_list(
                    folder_id or import_entity_data.get("entity_list_id")
                )
                entity_type = entity_list.entity_type
                listed_ids = await list_items.get_entity_ids(
                    entity_list,
                    import_entity_data.get("entity_id"),
                    import_entity_data.get("folder_path"),
                    import_entity_data.get("name"),
                    update_all_duplicates,
                )
                attrib = _json_ready(import_entity_data.get("attrib") or {})
                added = updated = commented = 0
                for listed_id in listed_ids:
                    item_id = list_items.get_item_id(entity_list, listed_id)
                    if item_id:
                        if existing_strategy != ExistingItemStrategy.UPDATE:
                            raise BadRequestException("Item is already in the list")
                        if attrib:
                            await list_items.update(entity_list, item_id, attrib)
                            updated += 1
                    elif update_only:
                        continue
                    else:
                        await list_items.add(entity_list, listed_id, attrib)
                        added += 1
                    if comment:
                        pending_comments.append(
                            (entity_type, listed_id, comment, comment_category)
                        )
                        commented += 1

                if not (added or updated or commented):
                    raise RowSkippedException(
                        f"The {entity_type} is not in the list"
                        if update_only
                        else "Already in the list"
                    )
                import_status.created += added
                import_status.updated += updated
                import_status.comments += commented
                unprocessed -= 1
                continue

            if "path" in import_entity_data and import_entity_data["path"]:
                path = import_entity_data["path"]

            entity_id = (
                matched_ids[0] if matched_ids else None
            ) or await _resolve_entity_id(
                row=import_entity_data,
                path_to_ids=path_to_ids,
                existing_identifiers=existing_identifiers,
                model_cls=model_cls,
                entity_cls=entity_cls,
                project_name=project_name,
            )

            if not entity_id and update_only:
                if import_type == "hierarchy":
                    _, matched_ids = await existing_hierarchy.match(
                        entity_type,
                        path,
                        import_entity_data.get("name"),
                        update_all_duplicates,
                    )
                    entity_id = matched_ids[0]
                else:
                    label = path or import_entity_data.get("name")
                    raise RowSkippedException(
                        f"No existing {entity_type} '{label}'"
                        if label
                        else f"No existing {entity_type} matches this row"
                    )

            if entity_id:
                if existing_strategy != ExistingItemStrategy.UPDATE:
                    identifier = path or identifier
                    raise BadRequestException(f"Item '{identifier}' already exists.")

            original_id = row.get("id")
            parent_id, parent_path = await _resolve_parent_id(
                row=import_entity_data,
                originals_and_new=originals_and_new,
                existing_identifiers=existing_identifiers,
                path_to_ids=path_to_ids,
                project_name=project_name,
                folder_id=folder_id,
            )
            if parent_id and parent_path:
                path_to_ids[parent_path] = parent_id
                import_entity_data[model_cls.parent_column_name()] = parent_id

            # for tasks
            if folder_id:
                import_entity_data[model_cls.parent_column_name()] = folder_id

            await _check_all_required(required_fields, import_entity_data)

            # Add project_name for non-user entities
            if entity_cls != UserEntity:
                import_entity_data["project_name"] = project_name

            # Remove entity_type from import_entity_data if present,
            # as its not a field to set
            import_entity_data.pop("entity_type", None)

            if import_entity_data.get("path") and not import_entity_data.get("name"):
                import_entity_data["name"] = (
                    import_entity_data["path"].rsplit("/", 1)
                )[-1]

            # Too noisy
            # logger.debug(
            #     f"entity_id:: {entity_id}:{entity_type} -> {import_entity_data} "
            # )

            target_ids = matched_ids or ([entity_id] if entity_id else [])
            if entity_id:
                has_changes = _has_changes(
                    row_values,
                    locators={*model_cls.unique_fields(), "path", "entity_type"},
                    path=path,
                    matched_by_name=bool(matched_ids) and not path,
                )
                if not has_changes and not comment:
                    raise RowSkippedException("Nothing to update")
                for target_id in target_ids if has_changes else []:
                    # mark that model has custom update
                    custom_updated = await model_cls.update(
                        user=user, preview=preview, **import_entity_data
                    )
                    if custom_updated:
                        import_status.updated += 1
                    elif operations is not None:
                        _merge_update(
                            pending_updates.setdefault((entity_type, target_id), {}),
                            import_entity_data,
                        )
            else:
                await _provide_default_values(
                    entity_cls, import_entity_data, cast("str", default_task_type)
                )

                entity_id = await model_cls.create(
                    user=user, preview=preview, **import_entity_data
                )
                if not entity_id and operations is not None:
                    entity_id = create_uuid()
                    queued_creates += 1
                    operations.create(
                        cast(ProjectLevelEntityType, entity_type),
                        entity_id=entity_id,
                        **import_entity_data,
                    )
                import_status.created += 1
                target_ids = [entity_id]

            if comment:
                for target_id in target_ids:
                    pending_comments.append(
                        (entity_type, target_id, comment, comment_category)
                    )
                import_status.comments += len(target_ids)

            if original_id and entity_id:
                originals_and_new[original_id] = entity_id
            if path:
                path_to_ids[path] = entity_id

            unprocessed -= 1

        except RowSkippedException as exp:
            import_status.skipped_items[f"{row_number}"] = str(exp)
            import_status.skipped += 1
            unprocessed -= 1
            continue

        except Exception as exp:
            logger.trace("Error processing row {} - {}", row_number, exp)
            status_str = "with errors"
            error_msg = str(exp)
            import_status.failed_items[f"{row_number}"] = error_msg

            unprocessed -= 1
            # ImportRowErrorException always stops processing
            if isinstance(exp, ImportRowErrorException):
                import_status.failed += 1
                import_status.skipped += unprocessed
                # Send end event for early termination
                phase_label = import_status.phase.capitalize()
                await EventStream.update(
                    event_id,
                    project=project_name,
                    description=f"{phase_label} finished with error",
                    progress=100,
                    summary=await _prepare_status_summary(import_status),
                    status="finished",
                    store=True,
                )
                return import_status
            import_status.skipped += 1
            continue

    import_status.updated += len(pending_updates)
    if operations is not None:
        for (update_type, update_id), payload in pending_updates.items():
            operations.update(
                cast(ProjectLevelEntityType, update_type), update_id, **payload
            )

    async def handle_progress(progress: OperationsProgress):
        if progress.operation.type == "create":
            import_status.created += 1
        elif progress.operation.type == "update":
            import_status.updated += 1

        import_status.phase = "importing"

        current_progress, trigger_update = _trigger_status_update(
            progress.index, progress.total
        )

        if trigger_update:
            await EventStream.update(
                event_id,
                project=project_name,
                description=f"Committing operation {progress.index}/{progress.total}",
                summary=await _prepare_status_summary(import_status),
                status="in_progress",
                progress=current_progress,
                store=True,
            )

    committed = preview or operations is None
    if not preview and operations is not None:
        # Operations count their creates and updates again while committing,
        # the ones done by the models themselves (users, lists) stay
        import_status.created -= queued_creates
        import_status.updated -= len(pending_updates)
        own_created, own_updated = import_status.created, import_status.updated

        start_time = time.perf_counter()
        try:
            response = await operations.process(
                progress_handler=handle_progress, wait_for_events=False
            )
            if not response.success:
                log_traceback("Failed to import data")
            committed = response.success
        except Exception as exp:
            log_traceback(f"Exception during import operations processing: {exp}")
            import_status.failed_items["global"] = (
                f"Import failed during operations processing: {exp}"
            )
            import_status.failed = len(rows)
            # transaction rollback
            import_status.created = own_created
            import_status.updated = own_updated
            status_str = "with rolled back updates"

        duration = time.perf_counter() - start_time
        processed_rows = import_status.created + import_status.updated
        avg_time_per_op = duration / processed_rows if processed_rows > 0 else 0

        logger.debug(
            f"Process completed in {duration:.2f} seconds. "
            f"Average time per operation: {avg_time_per_op:.4f} seconds "
            f"(Total rows: {processed_rows})."
        )

    if not preview and list_items is not None and committed:
        try:
            await list_items.save()
            import_status.entity_list_id = list_items.created_list_id
        except Exception as exp:
            log_traceback(f"Failed to save imported list items: {exp}")
            import_status.failed_items["list"] = f"Saving the list failed: {exp}"
            import_status.created = import_status.updated = 0
            status_str = "with errors"
            committed = False

    if not preview and pending_comments and project_name:
        # comments go to entities that exist now, so only after a commit
        import_status.comments = 0
        if not committed:
            import_status.failed_items["comments"] = (
                "Comments were not added because the import failed"
            )
        for index, (comment_type, comment_entity_id, body, category) in enumerate(
            pending_comments if committed else [], start=1
        ):
            try:
                entity = await get_entity_class(comment_type).load(
                    project_name, comment_entity_id
                )
                await create_activity(
                    entity=entity,
                    activity_type="comment",
                    body=body,
                    user=user,
                    data={"category": category} if category else None,
                    sender_type=SENDER_TYPE,
                    bump_entity_updated_at=True,
                )
                import_status.comments += 1
            except Exception as exp:
                status_str = "with errors"
                import_status.failed_items[f"comment {index}"] = (
                    f"Comment on {comment_type} {comment_entity_id} failed: {exp}"
                )

            current_progress, trigger_update = _trigger_status_update(
                index, len(pending_comments)
            )
            if trigger_update:
                await EventStream.update(
                    event_id,
                    project=project_name,
                    description=f"Adding comment {index}/{len(pending_comments)}",
                    summary=await _prepare_status_summary(import_status),
                    status="in_progress",
                    progress=current_progress,
                    store=False,
                )

    logger.debug(f"Import completed:{import_status}")
    await EventStream.update(
        event_id,
        project=project_name,
        description=f"{import_status.phase.capitalize()} finished {status_str}",
        summary=await _prepare_status_summary(import_status),
        status="finished" if len(import_status.failed_items) == 0 else "failed",
        store=True,
    )

    return import_status


async def _get_entity_type(
    project_name: str | None,
    row: dict[str, Any],
    column_mapping: list[ColumnMapping],
    importable_column_by_key: dict[str, ImportableColumn],
    value_mapping_by_key: dict[str, dict[str, ColumnValueMapping]],
    required: bool = True,
) -> str | None:
    """Extract the entity type from column mapping for hierarchy imports.

    Args:
        project_name: The project name for enum validation
        row: CSV row data
        column_mapping: List of ColumnMapping objects provided by the user
        importable_column_by_key: Pre-built lookup of field key to ImportableColumn
        value_mapping_by_key: Pre-built value mapping dicts per target key
        required: Raise if the entity type is not mapped or empty,
            otherwise return None
    """
    target_mapping_by_key = {
        mapping.target_key: mapping
        for mapping in column_mapping
        if mapping.action != "skip"
    }
    entity_type_mapping = target_mapping_by_key.get("entity_type")
    if not entity_type_mapping:
        if not required:
            return None
        raise BadRequestException(
            "Missing column mapping for 'entity_type' in hierarchy import"
        )

    import_entity_data: dict[str, Any] = {}
    await _remap_single_column(
        project_name=project_name,
        mapping=entity_type_mapping,
        row=row,
        import_entity_data=import_entity_data,
        column_name="entity_type",
        importable_column_by_key=importable_column_by_key,
        value_mapping=value_mapping_by_key.get("entity_type"),
    )
    entity_type = import_entity_data.get("entity_type")
    if not entity_type and required:
        raise BadRequestException("Missing entity type")
    return entity_type


async def _get_match_keys(
    project_name: str | None,
    row: dict[str, Any],
    column_mapping: list[ColumnMapping],
    importable_column_by_key: dict[str, ImportableColumn],
    value_mapping_by_key: dict[str, dict[str, ColumnValueMapping]],
) -> tuple[str | None, str | None]:
    """Return the path and name of a hierarchy row, before its entity type is known."""
    keys: dict[str, Any] = {}
    for mapping in column_mapping:
        if mapping.action == "skip" or mapping.target_key not in ("path", "name"):
            continue
        await _remap_single_column(
            project_name=project_name,
            mapping=mapping,
            row=row,
            import_entity_data=keys,
            importable_column_by_key=importable_column_by_key,
            value_mapping=value_mapping_by_key.get(mapping.target_key),
        )
    return keys.get("path") or None, keys.get("name") or None


def _has_changes(
    values: dict[str, Any],
    locators: set[str],
    path: str | None,
    matched_by_name: bool,
) -> bool:
    """Whether a row sets anything beyond the values that locate its entity."""
    for key, value in values.items():
        if key in locators:
            continue
        if key == "name" and (
            matched_by_name or (path and value == path.rsplit("/", 1)[-1])
        ):
            continue
        return True
    return False


def _json_ready(values: dict[str, Any]) -> dict[str, Any]:
    """Make imported values storable in JSON, e.g. list item attributes."""
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in values.items()
    }


def _merge_update(target: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge one row's update into an entity's pending update, later rows win."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key] = {**target[key], **value}
        else:
            target[key] = value


class _CommentChecker:
    """Validates imported comments and their categories.

    Categories come live from the project settings, so they are loaded
    once per import and matched case-insensitively.
    """

    def __init__(self, project_name: str | None, user: UserEntity):
        self.project_name = project_name
        self.user = user
        self._categories: dict[str, str] | None = None
        self._writable: set[str] | None = None

    async def _load(self) -> None:
        if self._categories is not None or not self.project_name:
            return
        categories = await ActivityCategories.get_activity_categories(self.project_name)
        self._categories = {
            category["name"].lower(): category["name"] for category in categories
        }
        if not self.user.is_manager:
            project = await ProjectEntity.load(self.project_name)
            self._writable = set(
                await ActivityCategories.get_accessible_categories(
                    self.user, project=project, level=EntityAccessHelper.UPDATE
                )
            )

    async def check(self, body: str, category: str | None) -> str | None:
        """Raise if the comment can't be added, return the category to use."""
        if len(body) > MAX_BODY_LENGTH:
            raise BadRequestException(
                f"Comment is longer than {MAX_BODY_LENGTH} characters"
            )
        if not category:
            return None
        await self._load()
        name = (self._categories or {}).get(str(category).strip().lower())
        if name is None:
            raise BadRequestException(f"Unknown comment category '{category}'")
        if self._writable is not None and name not in self._writable:
            raise ForbiddenException(f"You cannot use comment category '{name}'")
        return name


class _ExistingHierarchy:
    """Finds existing folders and tasks for update-only hierarchy imports."""

    def __init__(self, project_name: str | None):
        self.project_name = project_name
        self._ids_by_name: dict[str, dict[str, list[str]]] | None = None

    async def _get_ids_by_name(self) -> dict[str, dict[str, list[str]]]:
        if self._ids_by_name is None:
            self._ids_by_name = {}
            for entity_type in HIERARCHY_MODEL_CLASSES:
                index: dict[str, list[str]] = {}
                table = f"project_{self.project_name}.{entity_type}s"
                for record in await Postgres.fetch(f"SELECT id, name FROM {table}"):
                    index.setdefault(record["name"], []).append(record["id"])
                self._ids_by_name[entity_type] = index
        return self._ids_by_name

    async def match(
        self,
        entity_type: str | None,
        path: str | None,
        name: str | None,
        allow_many: bool = False,
    ) -> tuple[str, list[str]]:
        """Return entity type and ids of the folders or tasks matching the row.

        Matches by path, or by name when there is no path. Without an entity
        type both folders and tasks are searched. A name matching several
        entities is an error unless allow_many is set; matches of both
        folders and tasks always are, as one row cannot update both.
        """
        entity_types = [entity_type] if entity_type else list(HIERARCHY_MODEL_CLASSES)
        label = " or ".join(entity_types)
        matches: list[tuple[str, str]] = []

        if path:
            for candidate_type in entity_types:
                if candidate_type == "task" and "/" not in path.strip("/"):
                    continue
                try:
                    entity_id = await get_entity_id_by_path(
                        self.project_name, path, candidate_type == "task"
                    )
                except NotFoundException:
                    continue
                matches.append((candidate_type, entity_id))
            if not matches:
                raise RowSkippedException(f"No {label} with path '{path}'")
            if len(matches) > 1:
                raise BadRequestException(
                    f"Path '{path}' matches both a folder and a task, "
                    "map an Entity type column to pick one"
                )
            return matches[0][0], [matches[0][1]]

        if not name:
            raise RowSkippedException(f"No path or name to match a {label}")

        ids_by_name = await self._get_ids_by_name()
        for candidate_type in entity_types:
            matches.extend(
                (candidate_type, entity_id)
                for entity_id in ids_by_name[candidate_type].get(name, [])
            )
        if not matches:
            raise RowSkippedException(f"No {label} named '{name}'")
        counts = Counter(candidate_type for candidate_type, _ in matches)
        found = " and ".join(
            f"{count} {candidate_type}{'s' if count > 1 else ''}"
            for candidate_type, count in counts.items()
        )
        if len(counts) > 1:
            raise BadRequestException(
                f"Name '{name}' matches {found}, map an Entity type column to pick one"
            )
        if len(matches) > 1 and not allow_many:
            raise BadRequestException(
                f"Name '{name}' matches {found}, "
                "map a Path column to pick one or choose to update all matches"
            )
        return matches[0][0], [entity_id for _, entity_id in matches]


def _parse_csv_rows(file_bytes: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse CSV file and return header and rows.

    Args:
        file_bytes: Raw bytes content of the CSV file

    Returns:
        Tuple of (header_fields, list of row dictionaries)
    """
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = file_bytes.decode("latin-1")

    if not content.strip():
        return [], []

    # Initialize the sniffer
    sniffer = csv.Sniffer()

    try:
        dialect = sniffer.sniff(content[:4048], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)

    header = list(reader.fieldnames) if reader.fieldnames else []
    rows = list(reader)

    return header, rows


def _is_row_empty(row: dict[str, Any]) -> bool:
    """Check if a CSV row is completely empty (all values are None or empty).

    Args:
        row: Dictionary representing a CSV row

    Returns:
        True if the row is empty, False otherwise
    """
    return all(
        value is None or (isinstance(value, str) and not value.strip())
        for value in row.values()
    )


async def _remap_single_column(
    project_name: str | None,
    mapping: ColumnMapping,
    row: dict[str, Any],
    import_entity_data: dict[str, Any],
    column_name: str | None = None,
    importable_column_by_key: dict[str, ImportableColumn] | None = None,
    value_mapping: dict[str, ColumnValueMapping] | None = None,
    fields: list[ImportableColumn] | None = None,
) -> None:
    """Remap a single CSV column value based on its mapping.

    This is a reusable helper that processes one column from a row,
    applying value maps, type conversion, and enum validation.

    Args:
        project_name: The project name for enum validation (can be None)
        mapping: ColumnMapping object defining source->target mapping
        row: CSV row data
        import_entity_data: Dictionary to populate with converted values
        column_name: Optional override for target column name
        importable_column_by_key: Pre-built lookup of field key to ImportableColumn
        value_mapping: Pre-built value mapping dict for this column
        fields: Available importable columns (used only if
                importable_column_by_key is not provided)
    """
    target_column_name = column_name or mapping.target_key
    csv_column_name = mapping.source_key

    if importable_column_by_key is None:
        if fields is None:
            raise ValueError(
                "Either importable_column_by_key or fields must be provided"
            )
        importable_column_by_key = {
            importable_column.key: importable_column for importable_column in fields
        }
    importable_column = importable_column_by_key.get(target_column_name)
    if not importable_column:
        logger.debug(f"Unknown column '{target_column_name}'")
        return

    if value_mapping is None:
        value_mapping = {(vm.source or ""): vm for vm in mapping.values_mapping}

    # Get the value from the row
    source_value = row.get(csv_column_name)

    if target_column_name == "name" and source_value:
        source_value = source_value.replace("\\", "/").rsplit("/", 1)[-1]

    if target_column_name == "path" and source_value:
        source_value = source_value.replace("\\", "/").replace(" ", "")

    if importable_column.value_type == "list_of_strings" and source_value:
        val_str = str(source_value).strip()

        source_value = (
            [item.strip() for item in val_str.split(",") if item.strip()]
            if "," in val_str
            else [val_str]
        )
    else:
        source_value = [str(source_value)] if source_value is not None else []

    for val in source_value:
        if not val:
            val = "undefined"
        replacement_mapping = value_mapping.get(val)
        replacement_mapping_action = None

        # Apply value replacement if defined
        if replacement_mapping:
            if replacement_mapping.action == "skip":
                continue

            replacement_mapping_action = replacement_mapping.action
            val = replacement_mapping.target
        elif val == "undefined":
            continue

        target_value = _convert_value(importable_column, val)

        # Validate enum values if applicable
        if importable_column.enum_items:
            await _validate_enum_value(
                target_value,
                importable_column.enum_items,
                replacement_mapping_action,
                enum_name=getattr(importable_column, "enum_name", None),
                project_name=project_name,
            )

        # Store the value in import_entity_data
        _add_value_to_import_entity(
            import_entity_data=import_entity_data,
            column_name=target_column_name,
            column_type=importable_column.value_type,
            value=target_value,
        )


async def _remap_row(
    project_name: str | None,
    header: list[str],
    import_entity_data: dict[str, Any],
    row: dict[str, Any],
    fields: list[ImportableColumn],
    column_mapping: list[ColumnMapping],
    entity_type: str | None = None,
) -> None:
    """Remap CSV row data to match target schema based on column mapping.

    Args:
        header: CSV column headers
        import_entity_data: Dictionary to populate with converted values
        row: CSV row data
        fields: Available importable columns
        column_mapping: User-defined column mappings
        entity_type: Known entity type of a hierarchy row, used to read a
            combined folder/task type column without an entity type column
    """
    # Create lookup dictionaries for efficient access
    source_mapping_by_key = {mapping.source_key: mapping for mapping in column_mapping}
    importable_column_by_key = {
        importable_column.key: importable_column for importable_column in fields
    }
    target_mapping_by_key = {mapping.target_key: mapping for mapping in column_mapping}
    # Pre-build value mapping dicts per column to avoid rebuilding per row
    value_mapping_by_key: dict[str, dict[str, ColumnValueMapping]] = {}
    for col_mapping in column_mapping:
        if col_mapping.action != "skip":
            value_mapping_by_key[col_mapping.target_key] = {
                (vm.source or ""): vm for vm in col_mapping.values_mapping
            }
    # Process each CSV column
    for csv_column_name in header:
        mapping = source_mapping_by_key.get(csv_column_name)
        if mapping is None or mapping.action == "skip":
            continue
        column_name = mapping.target_key
        error_handling_mode = mapping.error_handling_mode
        if column_name == HIERARCHY_UNIFIED_COLUMN and entity_type:
            column_name = f"{entity_type}_type"
        elif column_name == HIERARCHY_UNIFIED_COLUMN:
            mapping_for_entity_type = target_mapping_by_key.get("entity_type")
            if mapping_for_entity_type is None:
                raise BadRequestException(
                    f"Missing 'entity_type' mapping for hierarchy import in row: {row}"
                )

            entity_type_import_data: dict[str, Any] = {}
            await _remap_single_column(
                project_name=project_name,
                mapping=mapping_for_entity_type,
                row=row,
                import_entity_data=entity_type_import_data,
                column_name="entity_type",
                importable_column_by_key=importable_column_by_key,
                value_mapping=value_mapping_by_key.get("entity_type"),
            )
            entity_type = entity_type_import_data.get("entity_type")
            if not entity_type:
                raise BadRequestException(
                    f"Missing 'entity_type' value for hierarchy import in row: {row}"
                )
            if entity_type not in HIERARCHY_MODEL_CLASSES:
                raise BadRequestException(
                    f"Invalid 'entity_type' value '{entity_type}' for hierarchy "
                    f"import in row: {row}"
                )
            column_name = f"{entity_type}_type"
        try:
            await _remap_single_column(
                project_name=project_name,
                mapping=mapping,
                row=row,
                import_entity_data=import_entity_data,
                column_name=column_name,
                importable_column_by_key=importable_column_by_key,
                value_mapping=value_mapping_by_key.get(mapping.target_key),
            )
        except Exception as exp:
            error_msg = str(exp)
            if error_handling_mode == "abort":
                raise ImportRowErrorException(error_msg)
            elif error_handling_mode == "default":
                # Get the target column definition for default value
                importable_column = importable_column_by_key.get(column_name)
                if importable_column:
                    _add_value_to_import_entity(
                        import_entity_data=import_entity_data,
                        column_name=column_name,
                        column_type=importable_column.value_type,
                        value=importable_column.default_value,
                    )
            else:
                raise BadRequestException(error_msg)


def _convert_value(importable_column: ImportableColumn, value: str) -> Any:
    if not value:
        # Return None for typed columns to avoid empty string issues
        if importable_column.value_type not in ("string", None):
            return None
        return value

    # Convert value based on column type
    if importable_column.value_type == "datetime":
        return _parse_datetime(value)
    elif importable_column.value_type == "float":
        return float(value)
    elif importable_column.value_type == "integer":
        return int(value)
    elif importable_column.value_type == "boolean":
        return _to_bool(value)
    else:
        # Handle string or None value_type - return value as-is
        return value


_DATE_RE = re.compile(
    r"^(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})"
    r"(?:[ T,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)


def _parse_datetime(value: str) -> datetime:
    """Parse an imported date: ISO, or numbers separated by dots, slashes or dashes.

    The import dialog converts dates to ISO itself (it detects the day/month
    order per column), this is the fallback for other clients: year first,
    or day first, except with slashes, which are month first (10/1/2026 is
    October 1) unless the first number can only be a day.

    Values without a timezone are UTC, which is how AYON keeps dates: the
    date picker saves UTC midnight and the UI shows the UTC day. A naive
    midnight read as local time would show the day before east of UTC.
    """
    parsed = _parse_naive_datetime(value.strip())
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_naive_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    match = _DATE_RE.match(value)
    if not match:
        raise BadRequestException(f"Invalid date '{value}'")
    first, middle, last, hours, minutes, seconds = match.groups()
    if len(first) == 4:
        year, month, day = int(first), int(middle), int(last)
    elif len(first) <= 2 and len(last) in (2, 4):
        year = int(last) if len(last) == 4 else 2000 + int(last)
        if len(last) == 2 and int(last) >= 70:
            year -= 100
        month_first = "/" in value and int(first) <= 12
        month, day = int(first), int(middle)
        if not month_first:
            month, day = day, month
    else:
        raise BadRequestException(f"Invalid date '{value}'")

    try:
        return datetime(
            year, month, day, int(hours or 0), int(minutes or 0), int(seconds or 0)
        )
    except ValueError:
        raise BadRequestException(f"Invalid date '{value}'") from None


async def _validate_enum_value(
    value: str,
    enum_items: list[EnumItem],
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
        BadRequestException: If value is not in enum and not handled by 'create' action
        NotImplementedError: If 'create' action is not yet implemented
    """
    if not value:
        return

    valid_values = {str(item.value).lower() for item in enum_items}
    value = value.replace("_", " ")
    to_check = {value.lower()} if isinstance(value, str) else set(value)

    # Identify exactly which values are missing
    missing_values = to_check - valid_values

    if missing_values:
        logger.info(
            f"Missing enum values: {missing_values} | Action: {replacement_action}"
        )

        if replacement_action == "create":
            if not enum_name:
                raise BadRequestException(
                    "Cannot create enum items: enum name not provided. "
                    "Ensure the field has an associated enum resolver."
                )

            # Create new enum items
            new_item = EnumItem(
                value=value,
                label=value.title(),
            )
            await EnumRegistry.create_item(
                enum_name,
                new_item,
                project_name=project_name,
            )
            return
        missing_values_str = ", ".join(map(str, missing_values))
        raise BadRequestException(
            f"Import contains invalid enum values: {missing_values_str}"
        )


def _add_value_to_import_entity(
    import_entity_data: dict[str, Any],
    column_name: str,
    column_type: str | None,
    value: Any,
) -> None:
    """Add a value to the import_entity_data dictionary.

    Handles both simple fields and nested fields (attrib.field, data.field).
    Uses column_type to determine if the field should be stored as a list.

    Args:
        import_entity_data: The import_entity_data dictionary to modify
        column_name: The target column name
        column_type: The type of the column (e.g., "list_of_strings")
        value: The value to store
    """
    is_iterable = column_type in ("list_of_strings", "list")
    is_nested = "." in column_name

    # Get or create the target container
    if is_nested:
        main, key = column_name.split(".", 1)
        if main not in import_entity_data:
            import_entity_data[main] = {}
        container = import_entity_data[main]
        is_bool = key.startswith("is")
    else:
        container = import_entity_data
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
        BadRequestException: If a required field is missing
    """
    for req_field in required_fields:
        if req_field not in row or not row[req_field]:
            raise BadRequestException(f"Missing required field '{req_field}'")


async def _get_existing_identifiers(
    model: EntityExportImport, project_name: str | None = None
) -> set[tuple[str, ...]]:
    """Get existing entity identifiers from the database.

    Args:
        model: The entity model class
        project_name: Project name for project-specific tables

    Returns:
        Set of tuples representing unique identifiers
    """
    existing_items = await model.get_all_items(
        field_names=model.unique_fields(),
        as_csv=False,
        project_name=project_name,
    )
    existing_items = cast("list[dict[str, Any]]", existing_items)
    existing_identifiers = {
        tuple(item[field] for field in model.unique_fields()) for item in existing_items
    }
    return existing_identifiers


async def _resolve_entity_id(
    row: dict[str, Any],
    path_to_ids: dict[str, str],
    existing_identifiers: set[tuple[str, ...]],
    model_cls,
    entity_cls,
    project_name: str | None,
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
    # Check by unique fields
    identifier: tuple[str, ...] = ()
    for unique_field in model_cls.unique_fields():
        val = row.get(unique_field)
        if not val:
            # If a required unique field is missing, reset or handle error
            identifier = ()
            break
        identifier = (*identifier, str(val))

    if identifier in existing_identifiers:
        return identifier[0]  # Return the identifier

    # Check by path if path is provided and entity supports it
    if "path" in row and row["path"]:
        path = row["path"]

        # Check in-memory cache
        entity_id = path_to_ids.get(path)
        if entity_id:
            return entity_id

        # Look up in database
        is_task = entity_cls == TaskEntity
        try:
            entity_id = await get_entity_id_by_path(project_name, path, is_task)
            if entity_id:
                path_to_ids[path] = entity_id  # Cache it
                return entity_id
        except NotFoundException:
            logger.trace(f"Couldn't find entity for path '{path}'")

    return None


async def _resolve_parent_id(
    row: dict[str, Any],
    originals_and_new: dict[str, str],
    existing_identifiers: set[tuple[str, ...]],
    path_to_ids: dict[str, str],
    project_name: str | None,
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
    if project_name is None:
        return None, None

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

        parent_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else ""

        parent_id = path_to_ids.get(parent_path)
        if parent_path and parent_id is None:
            try:
                parent_id = await get_entity_id_by_path(
                    project_name,
                    parent_path,
                    False,  # Not a task
                )
            except NotFoundException:
                raise BadRequestException(
                    f"Parent path '{parent_path}' not found in "
                    f"project '{project_name}'",
                )

        return parent_id, parent_path

    return None, None


async def _provide_default_values(
    entity_cls: type, import_entity_data: dict[str, Any], default_task_type: str
):
    """Provides default values for new entities."""
    if entity_cls == FolderEntity and not import_entity_data.get("folder_type"):
        import_entity_data["folder_type"] = "Folder"

    if entity_cls == TaskEntity and not import_entity_data.get("task_type"):
        import_entity_data["task_type"] = default_task_type


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


async def _prepare_status_summary(
    import_status: ImportStatus,
) -> dict[str, int | str | dict[str, Any] | None]:
    """Returns field from model as dictionary."""
    return {
        "created": import_status.created,
        "updated": import_status.updated,
        "skipped": import_status.skipped,
        "failed": import_status.failed,
        "phase": import_status.phase,
        "failedItems": import_status.failed_items,
        "skippedItems": import_status.skipped_items,
        "entityListId": import_status.entity_list_id,
        "comments": import_status.comments,
    }


def _trigger_status_update(index: int, total: int) -> tuple[int, bool]:
    """Returns value of progress out of 100 and if event should be triggered"""
    if total <= 0:
        return 100, False

    current_progress = (index * 100) // total

    if index == 0:
        return current_progress, True

    prev_progress = ((index - 1) * 100) // total

    return current_progress, current_progress > prev_progress
