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

from typing import Any, cast

from pydantic import BaseModel, ValidationInfo, create_model, field_validator

from ayon_server.entities import ProjectEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.logging import logger
from ayon_server.models.dynamic_model import DynamicModel
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

_project_attrib_model: tuple[type[BaseModel], type[BaseSettingsModel]] | None = None


def get_project_attrib_model() -> type[BaseSettingsModel]:
    """Return the settings model of the project attributes.

    It is based on the project attribute model, which changes
    when the attributes are modified, so it is created on demand.
    """
    global _project_attrib_model
    attrib_model = ProjectEntity.model.attrib_model
    if _project_attrib_model is None or _project_attrib_model[0] is not attrib_model:
        settings_model = cast(
            type[BaseSettingsModel],
            create_model(
                "ProjectAttribModel",
                __base__=(attrib_model, BaseSettingsModel),
                __module__=__name__,
            ),
        )
        _project_attrib_model = (attrib_model, settings_model)
    return _project_attrib_model[1]


def __getattr__(name: str) -> Any:
    # Backwards compatibility: ProjectAttribModel used to be a module-level class
    if name == "ProjectAttribModel":
        return get_project_attrib_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


project_attrib_type = DynamicModel(get_project_attrib_model)


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

    attributes: project_attrib_type.annotation = SettingsField(  # type: ignore
        default_factory=project_attrib_type,
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


def _clear_anatomy_schema_cache() -> None:
    # Anatomy JSON schema contains the project attributes
    Anatomy.__dict__.get("__ayon_schema_cache__", {}).clear()


attribute_library.on_reload(_clear_anatomy_schema_cache)
