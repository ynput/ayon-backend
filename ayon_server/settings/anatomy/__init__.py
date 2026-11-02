__all__ = [
    "Anatomy",
    "EntityNaming",
    "FolderType",
    "LinkType",
    "Root",
    "Status",
    "Tag",
    "TaskType",
    "ProductBaseTypes",
]

from typing import Any

from pydantic import ValidationInfo, field_validator

from ayon_server.entities import ProjectEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.entities.models.attrib import validate_attrib
from ayon_server.logging import logger
from ayon_server.models.attrib_values import AttribDict
from ayon_server.settings.anatomy.entity_naming import EntityNaming
from ayon_server.settings.anatomy.folder_types import FolderType, default_folder_types
from ayon_server.settings.anatomy.link_types import LinkType, default_link_types
from ayon_server.settings.anatomy.product_base_types import ProductBaseTypes
from ayon_server.settings.anatomy.roots import Root, default_roots
from ayon_server.settings.anatomy.statuses import Status, default_statuses
from ayon_server.settings.anatomy.tags import Tag, default_tags
from ayon_server.settings.anatomy.task_types import TaskType, default_task_types
from ayon_server.settings.anatomy.templates import Templates
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField
from ayon_server.settings.validators import ensure_unique_names, ensure_unique_property


def __getattr__(name: str) -> Any:
    # Backwards compatibility: ProjectAttribModel used to be a module-level class
    if name == "ProjectAttribModel":
        return ProjectEntity.model.attrib_model
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class Anatomy(BaseSettingsModel):
    _layout = "root"
    _title = "Project anatomy"

    entity_naming: EntityNaming = SettingsField(
        default_factory=EntityNaming,
        title="Entity Naming",
        description="Settings for automatic entity name generation",
    )

    roots: list[Root] = SettingsField(
        default=default_roots,
        title="Roots",
        description="Setup root paths for the project",
    )

    templates: Templates = SettingsField(
        default_factory=Templates,
        title="Templates",
        description="Path templates configuration",
    )

    # Project attributes are configured at runtime, so they are not part
    # of the model schema (see the anatomy schema endpoint)
    attributes: dict[str, Any] = SettingsField(
        default_factory=dict,
        validate_default=True,
        title="Attributes",
        description="Attributes configuration",
    )

    folder_types: list[FolderType] = SettingsField(
        default_factory=lambda: default_folder_types,
        title="Folder types",
        description="Folder types configuration",
        example=[default_folder_types[0].model_dump()],
    )

    task_types: list[TaskType] = SettingsField(
        default_factory=lambda: default_task_types,
        title="Task types",
        description="Task types configuration",
        example=[default_task_types[0].model_dump()],
    )

    link_types: list[LinkType] = SettingsField(
        default_factory=lambda: default_link_types,
        title="Link types",
        description="Link types configuration",
        example=[default_link_types[0].model_dump()],
    )

    statuses: list[Status] = SettingsField(
        default_factory=lambda: default_statuses,
        title="Statuses",
        description="Statuses configuration",
        example=[default_statuses[0].model_dump()],
    )

    tags: list[Tag] = SettingsField(
        default_factory=lambda: default_tags,
        title="Tags",
        description="Tags configuration",
        example=[default_tags[0].model_dump()],
    )

    product_base_types: ProductBaseTypes = SettingsField(
        title="Product Types",
        default_factory=lambda: ProductBaseTypes(),  # type: ignore
    )

    @field_validator("attributes")
    @classmethod
    def validate_attributes(
        cls, value: dict[str, Any], info: ValidationInfo
    ) -> dict[str, Any]:
        # The anatomy lists all project attributes (with the defaults).
        # A new project stores them as its own values.
        # Stored values (STORED_VALUES_CONTEXT) are not validated again.
        return AttribDict(
            {
                **dict.fromkeys(a["name"] for a in attribute_library["project"]),
                **attribute_library.project_defaults,
                **validate_attrib("project", value, info.context),
            }
        )

    @field_validator("roots", "folder_types", "task_types", "statuses", "tags")
    @classmethod
    def ensure_unique_names(cls, value, info: ValidationInfo):
        ensure_unique_names(value, field_name=info.field_name)
        return value

    @field_validator("folder_types", "task_types", "statuses")
    @classmethod
    def ensure_unique_short_names(cls, value, info: ValidationInfo):
        field_name = info.field_name
        try:
            ensure_unique_property(value, "shortName", context=field_name or "")
        except Exception:
            logger.warning(f"Duplicate shortName found in project anatomy {field_name}")
        return value
