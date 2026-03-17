"""Data models for data import/export functionality."""

from enum import Enum
from typing import Any, Dict, List, Tuple, Optional, Set, Literal

from pydantic import BaseModel
from pydantic.fields import ModelField, FieldInfo

from ayon_server.types import Field, OPModel
from ayon_server.entities import UserEntity, FolderEntity, TaskEntity
from ayon_server.lib.postgres import Postgres


class ExistingItemStrategy(str, Enum):
    """Strategy for handling existing items during import."""
    SKIP = "skip"
    UPDATE = "update"
    FAIL = "fail"


# Type alias for existing strategy values
ExistingStrategyType = Literal["skip", "update", "fail"]


class ImportStatus(OPModel):
    """Status model for tracking import results."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    failed_items: Dict[str, Any] = Field(default_factory=dict)  # Dict of items that failed with error details (name -> error message)


class ImportUpload(OPModel):
    """Model for returning info about uploaded file.

    It is expected to be enhanced with preview data, fields (?) in the future.
    """
    id: str


class EntityExportImport:
    """Base model for exporting and importing entities.

    Subclasses can configure the following class attributes:
        _entity_model: The entity class (e.g., UserEntity, FolderEntity)
        _table_name: Table name for database queries (str)
        _unique_fields: List of field names that uniquely identify an entity
        _data_fields: Additional data fields to include (list of tuples)
    """

    _entity_model = None  # Entity model class
    _table_name = ""  # Table name for queries
    _unique_fields: List[str] = ["name"]  # Default unique fields
    _data_fields: List[Tuple[str, FieldInfo]] = []  # Additional data fields
    # Fields that are calculated during import and not stored in DB,
    # 'path' for example
    _calculated_fields: List[FieldInfo] = []
    _parent_column_name: Optional[str] = None  # Column name for parent reference

    @classmethod
    def unique_fields(cls) -> List[str]:
        return cls._unique_fields

    @classmethod
    def parent_column_name(cls) -> Optional[str]:
        """Return the column name for the parent reference.
        
        Returns:
            The column name (e.g., 'parent_id' for Folders, 'folder_id' for Tasks)
            or None if not applicable.
        """
        return cls._parent_column_name

    @classmethod
    def main(cls) -> List[ModelField]:
        """Return main fields from entity model"""
        if cls._entity_model is None:
            return []
        
        return [
            value
            for value in cls._entity_model.model.main_model.__fields__.values()
            if value.name not in ["attrib", "data", "own_attrib"] and
               value.name not in cls._entity_model.model.dynamic_fields
        ]

    @classmethod
    def attrib(cls) -> List[ModelField]:
        """Return attribute fields from entity model with 'attrib.' prefix."""
        if cls._entity_model is None:
            return []
        
        result: List[ModelField] = []
        for f in cls._entity_model.model.attrib_model.__fields__.values():
            # Create a copy with prefixed name
            new_field = ModelField(
                name=f"attrib.{f.name}",
                type_=getattr(f, 'type_', f.annotation),
                field_info=f.field_info,
                required=f.required,
                default=f.default,
                model_config=f.model_config,
                class_validators=getattr(f, 'class_validators', None),
            )
            result.append(new_field)
        return result

    @classmethod
    def data(cls) -> List[Tuple[str, FieldInfo]]:
        """Return data fields for auxiliary data."""
        return cls._data_fields

    @classmethod
    def fields(cls) -> List[Dict[str, Any]]:
        """Return model fields (public) plus fields derived from `_attrib`."""
        result: List[Dict[str, Any]] = []

        # Model fields (exclude private fields starting with underscore)
        all_fields = [
            field
            for source in [
                cls.main(),
                cls.attrib(),
                cls.data(),
                cls.__fields__.values(),
                cls._calculated_fields
            ]
            for field in source
        ]
        for field in all_fields:
            if isinstance(field, ModelField):
                name = field.name
                field_info = field.field_info
                annotation = field.annotation
                required = field.required
                default = field.default if not required else None
            elif isinstance(field, FieldInfo):
                # Handle FieldInfo directly (e.g., from _calculated_fields)
                name = getattr(field, "name", None) or getattr(field, "title")
                if not name:
                    # Skip FieldInfo without a name
                    continue
                name = name.lower()
                field_info = field
                annotation = getattr(field, "annotation", Any)
                required = getattr(field, "required", False)
                default = getattr(field, "default", None)
            elif isinstance(field, tuple) and len(field) == 2:
                name, field_info = field
                annotation = getattr(field_info, "annotation", Any)
                required = False
                default = getattr(field_info, "default", None)
            else:
                # unknown/unsupported item; skip
                continue

            if name.startswith("_"):
                continue

            field_dict: Dict[str, Any] = {
                "name": name,
                "type": str(annotation),
                "required": required,
            }

            if not required and default is not None:
                field_dict["default"] = default

            if field_info:
                if field_info.description:
                    field_dict["description"] = field_info.description
                if field_info.title:
                    field_dict["title"] = field_info.title

            result.append(field_dict)

        return result

    @classmethod
    async def get_all_items(
        cls,
        field_names: List[str],
        as_csv: bool = False,
        project_name: str = None,
        entity_ids: Tuple[str, List[str]] = None
    ) -> List[dict[str, Any]] | List[List[str]]:
        """Get all entities from the database.

        Args:
            field_names: List of field names to include. Supports prefixes like
                    'attrib.field' or 'data.field' to access nested values.
            as_csv: If True, returns CSV-compatible rows with header
            project_name: Project name for table resolution

        Returns:
            List of entity dictionaries or CSV rows (including header)
        """
        if field_names is None:
            fields = cls.fields()
            field_names = [
                field["name"] for field in fields
            ]

        # Resolve table name
        table_name = cls._table_name
        if project_name and "{project_name}" in table_name:
            table_name = table_name.format(project_name=project_name)

        where = ""
        query_values = []
        if entity_ids:
            id_field = entity_ids[0]
            id_list = entity_ids[1]
            placeholders = ", ".join(f"${i+1}" for i in range(len(id_list)))
            where = f"WHERE {id_field} IN ({placeholders})"
            query_values = id_list

        select_field_names = "*"
        join_str = ""
        if "path" in field_names:
            # If path is requested, we need to join with hierarchy table to get it
            matching_key_field = (
                "folder_id"  if cls._entity_model == TaskEntity else "id"
            )
            join_str = (
                f"LEFT JOIN project_{project_name}.hierarchy h "
                f"ON {table_name}.{matching_key_field} = h.id"
            )
            full_path = (
                "h.path"
                if cls._entity_model != TaskEntity
                else f"COALESCE(h.path, '') || '/' || {table_name}.name as path"
            )
            select_field_names = f"{table_name}.*, {full_path}"

        query = (
            f"SELECT {select_field_names} "
            f"FROM {table_name} "
            f"{join_str} "
            f"{where} ORDER BY name")
        rows = await Postgres.fetch(query, *query_values)

        if as_csv:
            # Create CSV rows with header
            csv_rows = [field_names]  # Header row
            for row in rows:
                csv_row = []
                for field_name in field_names:
                    value = _get_field_value(row, field_name)
                    csv_row.append(str(value) if value is not None else "")
                csv_rows.append(csv_row)
            return csv_rows

        # Return dictionaries
        items = []
        for row in rows:
            item = {}
            for field_name in field_names:
                item[field_name] = _get_field_value(row, field_name)
            items.append(item)
        return items


class UserExportImportModel(EntityExportImport):
    """Model used for exporting and importing user entities."""

    _entity_model = UserEntity
    _table_name = "public.users"
    _unique_fields = ["name"]
    _data_fields = [
        ("data.isAdmin", FieldInfo(default=False, title="Admin")),
        ("data.userPool", FieldInfo(default=False, title="User Pool")),
    ]
    _parent_column_name = None


class FolderExportImportModel(EntityExportImport):
    """Model used for exporting and importing folder entities."""

    _entity_model = FolderEntity
    _table_name = "project_{project_name}.folders"
    _unique_fields = ["id"]
    _data_fields = []
    _calculated_fields = [FieldInfo(default="", title="Path")]
    _parent_column_name = "parent_id"


class TaskExportImportModel(EntityExportImport):
    """Model used for exporting and importing task entities."""

    _entity_model = TaskEntity
    _table_name = "project_{project_name}.tasks"
    _unique_fields = ["id"]
    _data_fields = []
    _calculated_fields = [FieldInfo(default="", title="Path")]
    _parent_column_name = "folder_id"


class FolderTaskExportImportModel(EntityExportImport):
    """Model for exporting tasks with folder path information.
    
    Uses TaskEntity.base_get_query to fetch tasks with their folder paths
    from the hierarchy table.
    """

    _entity_model = TaskEntity
    _table_name = "project_{project_name}.tasks"
    _unique_fields = ["id"]
    _data_fields = []
    _parent_column_name = "folder_id"
    # Fields required to reconstruct hierarchy and folder paths during import
    _process_required_fields = ["path"]
    _calculated_fields = [FieldInfo(default="", title="Path", name="path")]

    @classmethod
    def fields(cls) -> List[Dict[str, Any]]:
        """Return task fields including folder_path."""
        if cls._entity_model is None:
            return []

        # Add entity_type field at first position
        result: List[Dict[str, Any]] = [
            {
                "name": "item_type",
                "type": "str",
                "required": True,
                "default": "task",
            }
        ]

        # Get fields from both models
        folder_fields = FolderExportImportModel.fields()
        task_fields = TaskExportImportModel.fields()

        # Combine and deduplicate by field name
        seen_names: Set[str] = {"item_type"}
        for field in folder_fields + task_fields:
            if isinstance(field, dict) and field.get("name"):
                field_name = field["name"]
                if field_name in cls._process_required_fields:
                    # Ensure required fields are included even if not in field_names
                    field["required"] = True
                if field_name not in seen_names:
                    seen_names.add(field_name)
                    result.append(field)
        return result

    @classmethod
    async def get_all_items(
        cls,
        field_names: List[str],
        as_csv: bool = False,
        project_name: str = None,
        entity_ids: Tuple[str, List[str]] = None
    ) -> List[dict[str, Any]] | List[List[str]]:
        """Get all tasks with folder path information.
        
        Calls get_all_items from FolderExportImportModel and TaskExportImportModel
        sequentially and orders items in hierarchy where Task with folder_id of X
        should be under Folder with id X.
        """
        if field_names is None:
            fields = cls.fields()
            field_names = [field["name"] for field in fields]

        # Get folders and tasks sequentially (as dictionaries, not CSV)
        folder_items: List[dict[str, Any]] = await FolderExportImportModel.get_all_items(
            field_names=field_names,
            as_csv=False,
            project_name=project_name,
            entity_ids=entity_ids,
        )

        # Determine task entity_ids if needed
        task_entity_ids = None
        if entity_ids:
            task_entity_ids = entity_ids

        task_items: List[dict[str, Any]] = await TaskExportImportModel.get_all_items(
            field_names=field_names,
            as_csv=False,
            project_name=project_name,
            entity_ids=task_entity_ids,
        )

        # Add entity_type to each item
        for folder in folder_items:
            folder["item_type"] = "folder"
        for task in task_items:
            task["item_type"] = "task"

        # Build lookup structures
        if "path" in field_names:
            result_items = await cls._build_hierarchy_by_ids_with_path(
                folder_items,
                task_items
            )
        else:
            result_items = await cls._build_hierarchy_by_ids(
                folder_items,
                task_items
            )

        if as_csv:
            # Create CSV rows with header
            csv_rows = [field_names]
            for item in result_items:
                csv_row = []
                for field in field_names:
                    value = item.get(field)
                    csv_row.append(str(value) if value is not None else "")
                csv_rows.append(csv_row)
            return csv_rows

        return result_items

    @classmethod
    async def _build_hierarchy_by_ids(cls, folder_items, task_items):
        folder_by_id: Dict[str, dict] = {folder["id"]: folder for folder in folder_items}
        children_by_parent_id: Dict[str, List[dict]] = {}
        for folder in folder_items:
            parent_id = folder.get("parent_id")
            if parent_id not in children_by_parent_id:
                children_by_parent_id[parent_id] = []
            children_by_parent_id[parent_id].append(folder)
        tasks_by_folder_id: Dict[str, List[dict]] = {}
        for task in task_items:
            folder_id = task.get("folder_id")
            if folder_id not in tasks_by_folder_id:
                tasks_by_folder_id[folder_id] = []
            tasks_by_folder_id[folder_id].append(task)
        # Build ordered list with folders and their children recursively
        result_items: List[dict[str, Any]] = []
        # Start with root folders (those with no parent)
        root_folders = children_by_parent_id.get(None, [])
        for root_folder in root_folders:
            cls._add_folder_and_children_by_ids(
                root_folder,
                result_items,
                children_by_parent_id,
                tasks_by_folder_id
            )
        # Handle orphan tasks (tasks with no valid folder_id)
        orphan_tasks = tasks_by_folder_id.get(None, [])
        result_items.extend(orphan_tasks)
        # Also add tasks whose folder_id doesn't exist in folders
        existing_folder_ids = set(folder_by_id.keys())
        for folder_id, tasks in tasks_by_folder_id.items():
            if folder_id is not None and folder_id not in existing_folder_ids:
                result_items.extend(tasks)
        return result_items

    @classmethod
    def _add_folder_and_children_by_ids(
        cls,
        folder: dict[str, Any],
        result_items: List[dict[str, Any]] = None,
        children_by_parent_id = None,
        tasks_by_folder_id = None
    ):
        """Recursively add folder and its children to result_items."""
        if result_items is None:
            result_items = []
        result_items.append(folder)
        folder_id = folder.get("id")
        # Add child folders
        child_folders = children_by_parent_id.get(folder_id, [])
        for child_folder in child_folders:
            cls._add_folder_and_children_by_ids(
                child_folder,
                result_items,
                children_by_parent_id,
                tasks_by_folder_id
            )
        # Add tasks under this folder
        tasks = tasks_by_folder_id.get(folder_id, [])
        result_items.extend(tasks)

    @classmethod
    async def _build_hierarchy_by_ids_with_path(
        cls, folder_items: List[Dict], task_items: List[Dict]
    ) -> List[Dict]:
        """
        Build hierarchy using natural path sorting.
        Folders are sorted by path; tasks are placed immediately after their parent folder.
        """
        all_items = [
            {**item, "_is_folder": True} for item in folder_items
        ] + [
            {**item, "_is_folder": False} for item in task_items
        ]

        # Sort by path first, then type (folders before tasks)
        def sort_key(item):
            path = item.get("path", "")
            # Folder priority (0) vs Task priority (1) ensures folder comes first
            priority = 0 if item.get("_is_folder") else 1
            return (path, priority)

        all_items.sort(key=sort_key)

        for item in all_items:
            item.pop("_is_folder", None)

        return all_items


def _get_field_value(row: dict[str, Any], field_name: str) -> Any:
    """Extract value from row based on field path.

    Supports prefixes like 'attrib.field' or 'data.field' to access
    nested dictionary values. Fields without prefix are checked against
    top-level row keys.

    Args:
        row: Database row dictionary
        field_name: Field name, possibly with prefix (e.g., 'attrib.email')

    Returns:
        The extracted value or None if not found
    """
    if "." in field_name:
        prefix, key = field_name.split(".", 1)
        return (
            row.get(prefix, {}).get(key)
            if isinstance(row.get(prefix), dict)
            else None)
    else:
        return row.get(field_name)


# Aliases for backward compatibility
EXPORTABLE_ENTITIES = {
    "user": UserExportImportModel,
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
    "hierarchy": FolderTaskExportImportModel,
}