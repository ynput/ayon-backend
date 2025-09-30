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

from pydantic import validator

from ayon_server.entities import ProjectEntity
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
from ayon_server.settings.validators import ensure_unique_names


class ProjectAttribModel(
    ProjectEntity.model.attrib_model,  # type: ignore
    BaseSettingsModel,
):
    pass


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

    attributes: ProjectAttribModel = SettingsField(
        default_factory=ProjectAttribModel,
        title="Attributes",
        description="Attributes configuration",
    )

    folder_types: list[FolderType] = SettingsField(
        default_factory=lambda: default_folder_types,
        title="Folder types",
        description="Folder types configuration",
        example=[default_folder_types[0].dict()],
    )

    task_types: list[TaskType] = SettingsField(
        default_factory=lambda: default_task_types,
        title="Task types",
        description="Task types configuration",
        example=[default_task_types[0].dict()],
    )

    link_types: list[LinkType] = SettingsField(
        default_factory=lambda: default_link_types,
        title="Link types",
        description="Link types configuration",
        example=[default_link_types[0].dict()],
    )

    statuses: list[Status] = SettingsField(
        default_factory=lambda: default_statuses,
        title="Statuses",
        description="Statuses configuration",
        example=[default_statuses[0].dict()],
    )

    tags: list[Tag] = SettingsField(
        default_factory=lambda: default_tags,
        title="Tags",
        description="Tags configuration",
        example=[default_tags[0].dict()],
    )

    product_base_types: ProductBaseTypes = SettingsField(
        title="Product Types",
        default_factory=lambda: ProductBaseTypes(),  # type: ignore
    )

    @validator("roots", "folder_types", "task_types", "statuses", "tags")
    def ensure_unique_names(cls, value, field):
        ensure_unique_names(value, field_name=field.name)
        return value
