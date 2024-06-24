from pydantic import Field, validator

from ayon_server.entities import ProjectEntity
from ayon_server.settings.anatomy.folder_types import FolderType, default_folder_types
from ayon_server.settings.anatomy.link_types import LinkType, default_link_types
from ayon_server.settings.anatomy.roots import Root, default_roots
from ayon_server.settings.anatomy.statuses import Status, default_statuses
from ayon_server.settings.anatomy.tags import Tag
from ayon_server.settings.anatomy.task_types import TaskType, default_task_types
from ayon_server.settings.anatomy.templates import Templates
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.validators import ensure_unique_names


class ProjectAttribModel(
    ProjectEntity.model.attrib_model,  # type: ignore
    BaseSettingsModel,
):
    pass


class Anatomy(BaseSettingsModel):
    _layout: str = "root"
    roots: list[Root] = Field(
        default=default_roots,
        title="Roots",
        description="Setup root paths for the project",
    )

    templates: Templates = Field(
        default_factory=Templates,
        title="Templates",
        description="Path templates configuration",
    )

    attributes: ProjectAttribModel = Field(
        default_factory=ProjectAttribModel,
        title="Attributes",
        description="Attributes configuration",
    )

    folder_types: list[FolderType] = Field(
        default_factory=lambda: default_folder_types,
        title="Folder types",
        description="Folder types configuration",
    )

    task_types: list[TaskType] = Field(
        default_factory=lambda: default_task_types,
        title="Task types",
        description="Task types configuration",
    )

    link_types: list[LinkType] = Field(
        default_factory=lambda: default_link_types,
        title="Link types",
        description="Link types configuration",
    )

    statuses: list[Status] = Field(
        default_factory=lambda: default_statuses,
        title="Statuses",
        description="Statuses configuration",
    )

    tags: list[Tag] = Field(
        default_factory=list,
        title="Tags",
        description="Tags configuration",
    )

    class Config:
        title = "Project anatomy"

    @validator("roots", "folder_types", "task_types", "statuses", "tags")
    def ensure_unique_names(cls, value, field):
        ensure_unique_names(value, field_name=field.name)
        return value
