"""Entity field definitions.

This module contains the top-level field definitions for the entities.
Each field has its own column in the database.

Fields `id`, `created_at` and `updated_at` as well as `attrib` and `data`
are not part of the definition, since they are added
automatically by ModelSet class.

See .generator.FieldDefinition model for more information on specifiing
field parameters.
"""

from ayon_server.entities.models.submodels import LinkTypeModel, RepresentationFileModel
from ayon_server.types import (
    ENTITY_ID_EXAMPLE,
    ENTITY_ID_REGEX,
    LABEL_REGEX,
    NAME_REGEX,
    PROJECT_NAME_REGEX,
    USER_NAME_REGEX,
)

project_fields = [
    # Name is not here, since it's added by ModelSet class
    # (it is used as a primary key)
    {
        "name": "code",
        "type": "string",
        "regex": PROJECT_NAME_REGEX,
        "example": "prj",
        "title": "Project code",
        "required": True,
    },
    {
        "name": "library",
        "type": "boolean",
        "default": False,
    },
    {
        "name": "folder_types",
        "type": "list_of_any",
        "factory": "list",
        "title": "Folder types",
        "example": [
            {"name": "Folder", "icon": "folder"},
            {"name": "Asset", "icon": "folder"},
            {"name": "Shot", "icon": "folder"},
        ],
    },
    {
        "name": "task_types",
        "type": "list_of_any",
        "factory": "list",
        "title": "Task types",
        "example": [
            {"name": "Rigging", "icon": "rig"},
            {"name": "Modeling", "icon": "model"},
        ],
    },
    {
        "name": "link_types",
        "list_of_submodels": LinkTypeModel,
        "title": "Link types",
        "example": [
            {
                "name": "reference|version|version",
                "link_type": "reference",
                "input_type": "version",
                "output_type": "version",
                "data": {
                    "color": "#ff0000",
                },
            },
        ],
    },
    {
        "name": "statuses",
        "type": "list_of_any",
        "factory": "list",
        "title": "Statuses",
        "example": [
            {"name": "Unknown"},
        ],
    },
    {
        "name": "tags",
        "type": "list_of_any",
        "factory": "list",
        "title": "Tags",
        "description": "List of tags available to set on entities.",
        "example": [
            {"name": "Unknown"},
        ],
    },
    {
        "name": "config",
        "type": "dict",
        "default": {},
        "title": "Project config",
    },
]

user_fields = [
    {
        "name": "ui_exposure_level",
        "type": "integer",
        "title": "UI Exposure Level",
        "example": 100,
        "dynamic": True,
    },
]


folder_fields = [
    {
        "name": "name",
        "type": "string",
        "required": True,
        "title": "Folder name",
        "regex": NAME_REGEX,
        "example": "bush",
    },
    {
        "name": "label",
        "type": "string",
        "title": "Folder label",
        "example": "bush",
        "regex": LABEL_REGEX,
    },
    {
        "name": "folder_type",
        "type": "string",
        "required": False,
        "title": "Folder type",
        "example": "Asset",
    },
    {
        "name": "parent_id",
        "type": "string",
        "title": "Parent ID",
        "description": "Parent folder ID in the hierarchy",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "thumbnail_id",
        "type": "string",
        "title": "Thumbnail ID",
        "required": False,
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "path",
        "type": "string",
        "title": "Path",
        "example": "/assets/characters/xenomorph",
        "dynamic": True,
    },
    {
        "name": "has_versions",
        "type": "boolean",
        "title": "Has versions",
        "example": True,
        "dynamic": True,
    },
]


task_fields = [
    {
        "name": "name",
        "type": "string",
        "required": True,
        "title": "Folder ID",
        "regex": NAME_REGEX,
        "example": "modeling",
    },
    {
        "name": "label",
        "type": "string",
        "title": "Task label",
        "regex": LABEL_REGEX,
        "example": "Modeling of a model",
    },
    {
        "name": "task_type",
        "type": "string",
        "required": True,
        "title": "Task type",
        "example": "Modeling",
    },
    {
        "name": "thumbnail_id",
        "type": "string",
        "title": "Thumbnail ID",
        "required": False,
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "assignees",
        "type": "list_of_strings",
        "title": "Assignees",
        "description": "List of users assigned to the task",
        "example": ["john_doe", "jane_doe"],
    },
    {
        "name": "folder_id",
        "type": "string",
        "title": "Folder ID",
        "description": "Folder ID",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "path",
        "type": "string",
        "title": "Path",
        "example": "/assets/characters/xenomorph/modeling",
        "dynamic": True,
    },
]


product_fields = [
    {
        "name": "name",
        "type": "string",
        "required": True,
        "description": "Name of the product",
        "regex": NAME_REGEX,
        "example": "modelMain",
    },
    {
        "name": "folder_id",
        "type": "string",
        "required": True,
        "title": "Folder ID",
        "description": "ID of the parent folder",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "product_type",
        "type": "string",
        "required": True,
        "title": "Product type",
        "description": "Product type",
        "regex": NAME_REGEX,
        "example": "modelMain",
    },
    {
        "name": "product_base_type",
        "type": "string",
        "required": False,
        "title": "Product base type",
        "description": "Product base type",
        "regex": NAME_REGEX,
        "example": "model",
    },
    {
        "name": "path",
        "type": "string",
        "title": "Path",
        "example": "/assets/characters/xenomorph/modelMain",
        "dynamic": True,
    },
]


version_fields = [
    {
        "name": "version",
        "type": "integer",
        "required": True,
        "title": "Version",
        "description": "Version number",
        "example": 1,
    },
    {
        "name": "product_id",
        "type": "string",
        "required": True,
        "title": "Product ID",
        "description": "ID of the parent product",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "task_id",
        "type": "string",
        "required": False,
        "title": "Task ID",
        "description": "",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "thumbnail_id",
        "type": "string",
        "title": "Thumbnail ID",
        "required": False,
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "author",
        "type": "string",
        "regex": USER_NAME_REGEX,
        "example": "john_doe",
    },
    {
        "name": "path",
        "type": "string",
        "title": "Path",
        "example": "/assets/characters/xenomorph/modelMain/v003",
        "dynamic": True,
    },
]


representation_fields = [
    {
        "name": "name",
        "type": "string",
        "required": True,
        "title": "Name",
        "description": "The name of the representation",
        "example": "ma",
        "regex": NAME_REGEX,
    },
    {
        "name": "version_id",
        "type": "string",
        "required": True,
        "title": "Version ID",
        "description": "ID of the parent version",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "files",
        "list_of_submodels": RepresentationFileModel,
        "title": "Files",
        "description": "List of files",
    },
    {
        "name": "traits",
        "type": "dict",
        "title": "Traits",
        "description": "Dict of traits",
        "example": {
            "ayon.2d.PixelBased.v1": {
                "display_window_width": 1920,
                "display_window_height": 1080,
            },
            "ayon.2d.Image.v1": {},
        },
    },
    {
        "name": "path",
        "type": "string",
        "title": "Path",
        "example": "/assets/characters/xenomorph/modelMain/v003/ma",
        "dynamic": True,
    },
]

workfile_fields = [
    {
        "name": "path",
        "type": "string",
        "required": True,
        "title": "Path",
        "description": "Path to the workfile",
        "example": "{root['work']}/Project/workfiles/ma/modelMain_v001.ma",
    },
    {
        "name": "task_id",
        "type": "string",
        "required": True,
        "title": "Task ID",
        "description": "ID of the parent task",
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "thumbnail_id",
        "type": "string",
        "title": "Thumbnail ID",
        "required": False,
        "regex": ENTITY_ID_REGEX,
        "example": ENTITY_ID_EXAMPLE,
    },
    {
        "name": "created_by",
        "type": "string",
        "regex": NAME_REGEX,
        "example": "john_doe",
    },
    {
        "name": "updated_by",
        "type": "string",
        "regex": NAME_REGEX,
        "example": "john_doe",
    },
]
