"""Data models for data import/export functionality."""

from enum import StrEnum
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    Iterable,
)

from pydantic import BaseModel
from pydantic.fields import FieldInfo, ModelField

from api.data_import.common import SENDER_TYPE, _get_entity_id_by_path
from ayon_server.entities import FolderEntity, TaskEntity, UserEntity, VersionEntity
from ayon_server.entities.models.generator import FIELD_TYPES
from ayon_server.entity_lists import EntityList
from ayon_server.entity_lists.models import EntityListItemModel
from ayon_server.enum import EnumItem, EnumRegistry
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import AttributeType, Field, OPModel
from ayon_server.utils import create_uuid

# Create reverse mapping: Python type -> AttributeType string
# This inverts FIELD_TYPES which maps AttributeType -> Python type
TYPE_TO_ATTR_TYPE: dict[type, str] = {v: k for k, v in FIELD_TYPES.items()}

# column name for unified folder/task type in hierarchy imports
HIERARCHY_UNIFIED_COLUMN = "folder_or_task_type"


class ExistingItemStrategy(StrEnum):
    """Strategy for handling existing items during import."""

    SKIP = "skip"
    UPDATE = "update"
    FAIL = "fail"


# Type alias for existing strategy values
ExistingStrategyType = Literal["skip", "update", "fail"]

# How to handle errors when importing data for this column.
# - "skip": skip the row if there is an error in this column.
# - "abort": abort the entire import if there is an error in this column.
# - "default": use a default value if there is an error in this column.
# - TBD: for status, can we use something to "create" a missing value on the fly?
ErrorHandlingMode = Literal["skip", "abort", "default"]


class ImportableColumn(OPModel):
    key: Annotated[
        str,
        Field(
            description=(
                "The key of the column, such as `name`, `attrib.priority`, etc."
            )
        ),
    ]

    label: Annotated[
        str,
        Field(
            description=(
                "The label of the column, such as `Name`, `Priority`, etc. "
                "This is used for display purposes only."
            )
        ),
    ]

    required: Annotated[bool, Field(description="If value in field is required")]

    value_type: Annotated[
        AttributeType,
        Field(
            description=(
                "The type of the value in this column. This is used to determine "
                "how to parse the value. "
                "For example: `name` column has type `string`, `assignees`"
                " `list_of_strings` etc."
            )
        ),
    ]

    default_value: Annotated[
        str | None, Field(description="If value in field is required")
    ]

    enum_items: Annotated[
        list[EnumItem] | None,
        Field(description=("A list of possible enum items for this column "
                           "(if set)")),
    ]

    enum_name: Annotated[
        str | None,
        Field(description=("The enum resolver name (e.g., 'statuses', "
                           "'folderTypes')")),
    ] = None

    error_handling_modes: Annotated[
        list[ErrorHandlingMode],
        Field(
            description=(
                "A list of possible error handling modes for this column. "
                "Every column can have different available modes: "
                "For example: `name` column cannot use `default`, because "
                "default name cannot be generated."
            )
        ),
    ]
    create_new_items: Annotated[
        bool,
        Field(
            description=(
                "Marker that new items can be created for frontend to decide "
                "if Create button should be offered. Entity_type cannot be "
                "created for example."
            )
        ),
    ] = True


class ColumnValueMapping(OPModel):
    """Value to value mapping mostly for enum fields"""

    source: Annotated[
        str | None,  # allow replacement of empty value with some default
        Field(description=("The source value from csv")),
    ]
    target: Annotated[
        str | None,
        Field(description=("The target value from csv")),
    ]
    action: Annotated[
        Literal["map", "skip", "create"],
        Field(description="Map, skip or create missing"),
    ]


class ColumnMapping(OPModel):
    """User configured mapping of source csv column to target db column"""

    source_key: Annotated[
        str,
        Field(
            description=(
                "The key of the column, such as `name`, `attrib.priority`, etc."
            )
        ),
    ]

    target_key: Annotated[
        str,
        Field(
            description=(
                "The key of the column, such as `name`, `attrib.priority`, etc."
            )
        ),
    ]

    action: Annotated[
        Literal["map", "skip"], Field(description="Map or skip whole column")
    ]

    error_handling_mode: Annotated[
        ErrorHandlingMode,
        Field(description="Handle errors in this column. 'abort' to stop import"),
    ]

    values_mapping: Annotated[
        list[ColumnValueMapping],
        Field(description="List of values mapping mostly for enum fields"),
    ]


# Reusable column definitions for hierarchy imports
ENTITY_TYPE_COLUMN = ImportableColumn(
    key="entity_type",
    label="Entity type",
    required=True,
    value_type="string",
    default_value="",
    error_handling_modes=["abort"],
    enum_name=None,
    enum_items=[
        EnumItem(value="folder", label="Folder"),
        EnumItem(value="task", label="Task"),
    ],
)

PATH_COLUMN = ImportableColumn(
    key="path",
    label="Path",
    required=True,
    value_type="string",
    default_value="",
    error_handling_modes=["abort"],
    enum_name=None,
    enum_items=None,
)


class ImportStatus(OPModel):
    """Status model for tracking import results."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    failed_items: dict[str, Any] = Field(
        default_factory=dict
    )  # Dict of items that failed with error details (name -> error message)
    preview: bool = False  # if import was run in regular or dry run mode


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

    _entity_model : type[Any] | None = None  # Entity model class
    _table_name = ""  # Table name for queries
    _unique_fields: list[str] = ["name"]  # Default unique fields
    _data_fields: list[ImportableColumn] = []  # Additional data fields
    # Fields that are calculated during import and not stored in DB,
    # 'path' for example
    _calculated_fields: list[ImportableColumn] = []
    # Column name for parent reference
    _parent_column_name: str | None = None
    # Field names to exclude from export/import
    # Subclasses can override by redefining this class attribute
    _excluded_field_names: set[str] = {
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "thumbnail_id",
        "creation_order",
    }

    @classmethod
    def unique_fields(cls) -> list[str]:
        return cls._unique_fields

    @classmethod
    def parent_column_name(cls) -> str | None:
        """Return the column name for the parent reference.

        Returns:
            The column name (e.g., 'parent_id' for Folders, 'folder_id' for Tasks)
            or None if not applicable.
        """
        return cls._parent_column_name

    @classmethod
    async def create(cls, **kwargs: Any) -> str | None:
        """Explicit create for entities without Operations

        Return value to skip ordinary usage of operations.
        """
        return None

    @classmethod
    async def update(cls, **kwargs: Any) -> str | None:
        """Explicit update for entities without Operations"""
        return None

    @classmethod
    def main(cls) -> list[ModelField]:
        """Return main fields from entity model"""
        if cls._entity_model is None:
            return []

        return [
            value
            for value in _get_model_fields(cls._entity_model.model.main_model).values()
            if value.name not in ["attrib", "data", "own_attrib"]
            and value.name not in cls._entity_model.model.dynamic_fields
        ]

    @classmethod
    def attrib(cls) -> list[ModelField]:
        """Return attribute fields from entity model with 'attrib.' prefix."""
        if cls._entity_model is None:
            return []

        result: list[ModelField] = []
        for f in _get_model_fields(cls._entity_model.model.attrib_model).values():
            # Create a copy with prefixed name
            new_field = ModelField(
                name=f"attrib.{f.name}",
                type_=getattr(f, "type_", f.annotation),
                field_info=f.field_info,
                required=f.required,
                default=f.default,
                model_config=f.model_config,
                class_validators=getattr(f, "class_validators", None),
            )
            result.append(new_field)
        return result

    @classmethod
    def data(cls) -> list[ImportableColumn]:
        """Return data fields for auxiliary data."""
        return cls._data_fields

    @classmethod
    async def fields(cls, project_name: str | None = None) -> list[ImportableColumn]:
        """Return model fields (public) plus fields derived from `_attrib`.

        Args:
            project_name: Project name for resolving project-specific enums.
        """
        result: list[ImportableColumn] = []

        sources: list[Iterable[Any]] = [
            cls.main(),
            cls.attrib(),
            cls.data(),
            cls._calculated_fields
        ]

        # Model fields (exclude private fields starting with underscore)
        all_fields = [
            field
            for source in sources
            for field in source
        ]
        for field in all_fields:
            name: str | None = None  # because of MyPy
            if isinstance(field, ModelField):
                name = field.name
                field_info = field.field_info
                annotation = field.annotation
                required = field.required
                default = field.default if not required else None
            elif isinstance(field, FieldInfo):
                # Handle FieldInfo directly (e.g., from _calculated_fields)
                # Note: 'name' may be stored in extra dict in pydantic v2
                name = getattr(field, "name", None)
                if name is None:
                    extra = getattr(field, "extra", {})
                    if isinstance(extra, dict):
                        name = extra.get("name")
                if name is None:
                    name = getattr(field, "title", None)
                if not name:
                    # Skip FieldInfo without a name
                    continue
                name = str(name).lower()
                field_info = field
                annotation = getattr(field, "annotation", Any)
                required = getattr(field, "required", False)
                default = getattr(field, "default", None)
            elif isinstance(field, tuple) and len(field) == 2:
                name, field_info = field
                annotation = getattr(field_info, "annotation", Any)
                required = False
                default = getattr(field_info, "default", None)
            elif isinstance(field, ImportableColumn):
                result.append(field)
                continue
            else:
                # unknown/unsupported item; skip
                continue

            if name.startswith("_"):
                continue

            if name in cls._excluded_field_names:
                continue

            # Get the label - use title if available, otherwise capitalize the name
            label = name
            if field_info and field_info.title:
                label = field_info.title

            # Convert annotation to valid AttributeType
            value_type = _get_attr_type_from_annotation(annotation)

            # Determine error handling modes based on field requirements
            # - "skip" and "abort" are always available
            # - "default" is only available for non-required fields
            error_handling_modes: list[str] = ["skip", "abort"]
            if not required:
                error_handling_modes.append("default")

            field_dict: dict[str, Any] = {
                "key": name,
                "label": label,
                "value_type": value_type,
                "required": required,
                "default_value": default,
                "error_handling_modes": error_handling_modes,
            }
            enum_items = None

            field_to_enum_names = {
                "status": "statuses",
                "folder_type": "folderTypes",
                "task_type": "taskTypes",
                "link_type": "linkTypes",
            }
            enum_name = field_to_enum_names.get(name) or name
            try:
                enum_items = await EnumRegistry.resolve(
                    enum_name, project_name=project_name
                )
            except BadRequestException:
                # do not log anything, would be polluting too much
                pass

            if enum_items:
                field_dict["enum_items"] = enum_items
                field_dict["enum_name"] = enum_name

            if field_info:
                if field_info.description:
                    field_dict["description"] = field_info.description
                if field_info.title:
                    field_dict["title"] = field_info.title

            column_info = ImportableColumn(**field_dict)

            result.append(column_info)

        return result

    @classmethod
    async def get_all_items(
        cls,
        field_names: list[str] | None,
        as_csv: bool = False,
        project_name: str | None = None,
        entity_ids: tuple[str, list[str]] | None = None,
    ) -> list[dict[str, Any]] | list[list[str]]:
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
            fields = await cls.fields()
            field_names = [field.key for field in fields]

        # Resolve table name
        table_name = cls._table_name
        if project_name and "{project_name}" in table_name:
            table_name = table_name.format(project_name=project_name)

        where = ""
        query_values = []
        if entity_ids:
            id_field = entity_ids[0]
            id_list = entity_ids[1]
            placeholders = ", ".join(f"${i + 1}" for i in range(len(id_list)))
            where = f"WHERE {id_field} IN ({placeholders})"
            query_values = id_list

        select_field_names = "*"
        join_str = ""
        if "path" in field_names:
            # If path is requested, we need to join with hierarchy table to get it
            matching_key_field = (
                "folder_id" if cls._entity_model == TaskEntity else "id"
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
            f"{where} ORDER BY name"
        )
        rows = await Postgres.fetch(query, *query_values)

        return await cls._return_items(as_csv, field_names, rows)

    @classmethod
    async def _return_items(cls, as_csv, field_names, rows):
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
        ImportableColumn(
            key="data.isAdmin",
            label="Admin",
            required=False,
            value_type="boolean",
            default_value="False",
            error_handling_modes=["skip", "default"],
            enum_name=None,
            enum_items=None,
        ),
        ImportableColumn(
            key="data.isDeveloper",
            label="Developer",
            required=False,
            value_type="boolean",
            default_value="False",
            error_handling_modes=["skip", "default"],
            enum_name=None,
            enum_items=None,
        ),
        # ImportableColumn(
        #     key="data.userPool",
        #     label="License",
        #     required=False,
        #     value_type="string",
        #     default_value="",
        #     error_handling_modes=["skip", "default"],
        #     enum_name=None,
        #     enum_items=[
        #         EnumItem(value=item.id, label=item.label)
        #         for item in  await AuthUtils.get_user_pools()
        #     ],
        # ),
    ]
    _parent_column_name = None

    @classmethod
    async def create(cls, **kwargs: Any) -> str | None:
        name = kwargs["name"]
        preview = kwargs.get("preview", False)

        user = UserEntity(payload={**kwargs})
        user.set_password(name)
        if not preview:
            await user.save()

        return name

    @classmethod
    async def update(cls, **kwargs: Any) -> str | None:
        preview = kwargs.get("preview", False)
        name = kwargs["name"]
        user = await UserEntity.load(name, for_update=True)
        if not user:
            raise NotFoundException(f"User '{name}' not found for update")
        user.data.update(kwargs.get("data", {}))
        # Pydantic models don't have an update method
        for key, value in kwargs.get("attrib", {}).items():
            setattr(user.attrib, key, value)
        if not preview:
            await user.save()

        return name


class FolderExportImportModel(EntityExportImport):
    """Model used for exporting and importing folder entities."""

    _entity_model = FolderEntity
    _table_name = "project_{project_name}.folders"
    _unique_fields = ["id"]
    _data_fields = []
    _calculated_fields = [
        ENTITY_TYPE_COLUMN,
        PATH_COLUMN,
    ]
    _parent_column_name = "parent_id"


class TaskExportImportModel(EntityExportImport):
    """Model used for exporting and importing task entities."""

    _entity_model = TaskEntity
    _table_name = "project_{project_name}.tasks"
    _unique_fields = ["id"]
    _data_fields = []
    _calculated_fields = [
        ENTITY_TYPE_COLUMN,
        PATH_COLUMN,
    ]
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
    _process_required_fields = ["entity_type", "path"]
    _calculated_fields = []

    @classmethod
    async def fields(cls, project_name: str | None = None) -> list[ImportableColumn]:
        """Return task fields including folder_path.

        Args:
            project_name: Project name for resolving project-specific fields and enums.
        """
        if cls._entity_model is None:
            return []

        # Add entity_type field at first position
        result: list[ImportableColumn] = []

        # Get fields from both models
        folder_fields = await FolderExportImportModel.fields(project_name=project_name)
        task_fields = await TaskExportImportModel.fields(project_name=project_name)

        process_columns = [
            ImportableColumn(
                key="entity_type",
                label="Entity type",
                required=True,
                value_type="string",
                default_value="",
                error_handling_modes=["abort"],
                enum_name=None,
                enum_items=[
                    EnumItem(value="folder", label="Folder"),
                    EnumItem(value="task", label="Task"),
                ],
                create_new_items=False,
            ),
            ImportableColumn(
                key="path",
                label="Path",
                required=True,
                value_type="string",
                default_value="",
                error_handling_modes=["abort"],
                enum_name=None,
                enum_items=None,
            ),
            # to use only single column in csv to contain both
            # folder and task types
            ImportableColumn(
                key=HIERARCHY_UNIFIED_COLUMN,
                label="Folder or Task type",
                required=False,
                value_type="string",
                default_value="",
                error_handling_modes=["abort"],
                enum_name=None,
                enum_items=None,
                create_new_items=False,
            ),
        ]

        label_overrides = {
            "status": "Status",
            "active": "Active",
            "id": "Id",
            "tags": "Tags",
            "name": "Name",
            "label": "Label",
        }
        # Combine and deduplicate by field name
        seen_names: set[str] = set()
        for field in folder_fields + task_fields + process_columns:
            # control required explicitly based on agreed format
            field.required = field.key in cls._process_required_fields
            label_override = label_overrides.get(field.key)
            field.label = label_override or field.label
            if field.key not in seen_names:
                seen_names.add(field.key)
                result.append(field)
        return result

    @classmethod
    async def get_all_items(
        cls,
        field_names: list[str] | None,
        as_csv: bool = False,
        project_name: str | None = None,
        entity_ids: tuple[str, list[str]] | None = None,
    ) -> list[dict[str, Any]] | list[list[str]]:
        """Get all tasks with folder path information.

        Calls get_all_items from FolderExportImportModel and TaskExportImportModel
        sequentially and orders items in hierarchy where Task with folder_id of X
        should be under Folder with id X.
        """
        if field_names is None:
            fields = await cls.fields()
            field_names = [field.key for field in fields]

        # Get folders and tasks sequentially (as dictionaries, not CSV)
        folder_items: list[dict[str, Any]] = cast(
            "list[dict[str, Any]]",
            await FolderExportImportModel.get_all_items(
                field_names=field_names,
                as_csv=False,
                project_name=project_name,
                entity_ids=entity_ids,
            ),
        )

        # Determine task entity_ids if needed
        task_entity_ids = None
        if entity_ids:
            task_entity_ids = entity_ids

        task_items: list[dict[str, Any]] = cast(
            "list[dict[str, Any]]",
            await TaskExportImportModel.get_all_items(
                field_names=field_names,
                as_csv=False,
                project_name=project_name,
                entity_ids=task_entity_ids,
            ),
        )

        # Add entity_type to each item
        for folder in folder_items:
            folder["entity_type"] = "folder"
        for task in task_items:
            task["entity_type"] = "task"

        # Build lookup structures
        if "path" in field_names:
            result_items = await cls._build_hierarchy_by_ids_with_path(
                folder_items, task_items
            )
        else:
            result_items = await cls._build_hierarchy_by_ids(folder_items, task_items)

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
    async def _build_hierarchy_by_ids(
        cls, folder_items: list[dict[str, Any]], task_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        folder_by_id: dict[str, dict[str, Any]] = {
            folder["id"]: folder for folder in folder_items
        }
        children_by_parent_id: dict[str | None, list[dict[str, Any]]] = {}
        for folder in folder_items:
            parent_id = folder.get("parent_id")
            if parent_id not in children_by_parent_id:
                children_by_parent_id[parent_id] = []
            children_by_parent_id[parent_id].append(folder)
        tasks_by_folder_id: dict[str | None, list[dict[str, Any]]] = {}
        for task in task_items:
            folder_id = task.get("folder_id")
            if folder_id not in tasks_by_folder_id:
                tasks_by_folder_id[folder_id] = []
            tasks_by_folder_id[folder_id].append(task)
        # Build ordered list with folders and their children recursively
        result_items: list[dict[str, Any]] = []
        # Start with root folders (those with no parent)
        root_folders = children_by_parent_id.get(None, [])
        for root_folder in root_folders:
            cls._add_folder_and_children_by_ids(
                root_folder, result_items, children_by_parent_id, tasks_by_folder_id
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
        result_items: list[dict[str, Any]] | None = None,
        children_by_parent_id=None,
        tasks_by_folder_id=None,
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
                child_folder, result_items, children_by_parent_id, tasks_by_folder_id
            )
        # Add tasks under this folder
        tasks = tasks_by_folder_id.get(folder_id, [])
        result_items.extend(tasks)

    @classmethod
    async def _build_hierarchy_by_ids_with_path(
        cls, folder_items: list[dict[str, Any]], task_items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Build hierarchy using natural path sorting.
        Folders are sorted by path; tasks are placed immediately after their
        parent folder.
        """
        all_items = [{**item, "_is_folder": True} for item in folder_items] + [
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


class EntityListExportImportModel(EntityExportImport):
    """Model used for exporting and importing task entities.

    More explicit in fields and get_all_items as `EntityListItemModel` is not a
    TopLevelModel (as FolderEntity for example)
    """

    _entity_model = EntityListItemModel
    _table_name = "project_{project_name}.entity_list_items"
    _unique_fields = []
    _data_fields = []
    _calculated_fields = []  # must be explicitly in fields
    _parent_column_name = "entity_list_id"

    @classmethod
    async def fields(
        cls, project_name: str | None = None
    ) -> list[ImportableColumn]:
        """Return model fields (public) plus fields derived from `_attrib`.

        Args:
            project_name: Project name for resolving project-specific enums.
        """
        result: list[ImportableColumn] = []

        result.append(
            ImportableColumn(
                key="entity_list_id",
                label="Entity List Id",
                required=False,
                value_type="string",
                default_value="",
                error_handling_modes=["abort"],
            )
        )

        result.append(
            ImportableColumn(
                key="entity_id",
                label="Entity Id",
                required=False,
                value_type="string",
                default_value="",
                error_handling_modes=["abort"],
            )
        )

        result.append(
            ImportableColumn(
                key="folder_path",
                label="Entity path",
                required=False,
                value_type="string",
                default_value="",
                error_handling_modes=["skip"],
            )
        )

        return result

    @classmethod
    async def get_all_items(
        cls,
        field_names: list[str] | None,
        as_csv: bool = False,
        project_name: str | None = None,
        entity_ids: tuple[str, list[str]] | None = None,
    ) -> list[dict[str, Any]] | list[list[str]]:
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
            fields = await cls.fields()
            field_names = [field.key for field in fields]

        where = ""
        if entity_ids:
            id_list = entity_ids[1]
            placeholders = ", ".join(f"${i + 1}" for i in range(len(id_list)))
            where = f"WHERE  li.entity_list_id IN ({placeholders})"

        query = (
            "SELECT li.entity_id, li.entity_list_id, "
            "CASE "
            "WHEN t.id IS NOT NULL THEN li.folder_path || '/' || t.name "
            "ELSE li.folder_path "
            "END AS folder_path "
            f"FROM project_{project_name}.entity_list_items li "
            f"LEFT JOIN project_{project_name}.tasks t "
            "ON li.entity_id = t.id "
            f"{where}"
        )
        rows = await Postgres.fetch(query)

        return await cls._return_items(as_csv, field_names, rows)

    @classmethod
    async def create(cls, **kwargs: Any) -> str | None:
        project_name = kwargs["project_name"]
        entity_list_id = kwargs["entity_list_id"]
        user = kwargs["user"]
        folder_path = kwargs.get("folder_path")
        entity_id = kwargs.get("entity_id")
        preview = kwargs.get("preview")

        if not folder_path and not entity_id:
            raise ValueError(
                "At least one of 'entity_id', or 'folder_path' must be provided."
            )

        async with Postgres.transaction():
            entity_list = await EntityList.load(project_name, entity_list_id, user=user)
            await entity_list.ensure_can_update()

            # folder paths might be folders or tasks
            if not entity_id:
                try:
                    entity_id = await _get_entity_id_by_path(
                        project_name, folder_path, is_task=False
                    )
                except NotFoundException:
                    entity_id = await _get_entity_id_by_path(
                        project_name, folder_path, is_task=True
                    )

            list_type = entity_list.entity_type
            try:
                if list_type == "folder":
                    await FolderEntity.load(project_name, entity_id)
                elif list_type == "task":
                    await TaskEntity.load(project_name, entity_id)
                elif list_type == "version":
                    await VersionEntity.load(project_name, entity_id)
                else:
                    raise ValueError(f"Unsupported entity type: {list_type}")
            except NotFoundException:
                raise NotFoundException(
                    f"Entity with id '{entity_id}' not found for type '{list_type}'"
                )

            # check if already in list
            for item in entity_list.items:
                if item.entity_id == entity_id:
                    return item.id

            new_id = create_uuid()
            await entity_list.add(
                id=new_id,
                entity_id=entity_id,
            )
            if not preview:
                await entity_list.save(
                    sender=f"{SENDER_TYPE}-create", sender_type=SENDER_TYPE
                )

        return new_id

    @classmethod
    async def update(cls, **kwargs: Any) -> str | None:
        # no sense in updating list item for now
        # currently only adding items to a list
        return "dummy"


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
            row.get(prefix, {}).get(key) if isinstance(row.get(prefix), dict) else None
        )
    else:
        return row.get(field_name)


def _get_model_fields(model: type[BaseModel]) -> dict[str, Any]:
    """Get fields from a Pydantic model, compatible with both v1 and v2.

    Pydantic v2 uses 'model_fields' while v1 uses '__fields__'.
    This helper provides compatibility with both versions.
    """
    if hasattr(model, "model_fields"):
        return model.model_fields
    return model.__fields__


def _get_attr_type_from_annotation(annotation: Any) -> str:
    """Convert a Python type annotation to an AttributeType string.

    Args:
        annotation: The Python type annotation (e.g., str, Optional[int], list[str])

    Returns:
        A valid AttributeType string (e.g., "string", "integer", "list_of_strings")
    """
    # Get the origin type (e.g., list for list[str])
    origin = get_origin(annotation)

    # Handle Optional (which is Union with None)
    if origin is Union:
        args = get_args(annotation)
        # Filter out NoneType to get the actual type
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            # Single non-None type, recursively check it
            return _get_attr_type_from_annotation(non_none_args[0])

    # Handle List types
    if origin is list:
        args = get_args(annotation)
        if args:
            elem_type = args[0]
            if elem_type is str:
                return "list_of_strings"
            elif elem_type is int:
                return "list_of_integers"
            elif elem_type is Any:
                return "list_of_any"
            else:
                return "list_of_submodels"
        return "list_of_any"

    # Handle basic types using the reverse mapping from FIELD_TYPES
    if annotation in TYPE_TO_ATTR_TYPE:
        return TYPE_TO_ATTR_TYPE[annotation]

    # Check if it's a direct type in our mapping (including Optional versions)
    for py_type, attr_type in TYPE_TO_ATTR_TYPE.items():
        if annotation == py_type or annotation == py_type | None:
            return attr_type

    # Handle Pydantic constrained types (e.g., conint, constrained integers
    # with gt/ge/lt/le)
    # Check if it's a subclass of int (includes constrained int types)
    try:
        if isinstance(annotation, type) and issubclass(annotation, int):
            return "integer"
    except TypeError:
        # annotation is not suitable for issubclass (e.g. not a class); ignore
        # and let the logic below handle it via origin checks or the fallback
        pass

    # Check origin for constrained types
    if origin is not None:
        # Get the underlying type from the origin
        origin_args = get_args(annotation)
        if origin_args:
            underlying = origin_args[0]
            if underlying is int or (
                isinstance(underlying, type) and issubclass(underlying, int)
            ):
                return "integer"

    # Default fallback
    return "string"


# Aliases for backward compatibility
EXPORTABLE_ENTITIES = {
    "user": UserExportImportModel,
    "folder": FolderExportImportModel,
    "task": TaskExportImportModel,
    "hierarchy": FolderTaskExportImportModel,
    "entity_list_item": EntityListExportImportModel,
}
