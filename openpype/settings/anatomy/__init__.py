from pydantic import Field, validator

from openpype.entities import ProjectEntity
from openpype.settings.anatomy.folder_types import FolderType, default_folder_types
from openpype.settings.anatomy.roots import Root, default_roots
from openpype.settings.anatomy.statuses import Status, default_statuses
from openpype.settings.anatomy.task_types import TaskType, default_task_types
from openpype.settings.anatomy.templates import Templates
from openpype.settings.common import BaseSettingsModel, ensure_unique_names


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

    attributes: ProjectAttribModel = Field(  # type: ignore
        default_factory=ProjectAttribModel,
        title="Attributes",
        description="Attributes configuration",
    )

    folder_types: list[FolderType] = Field(
        default=default_folder_types,
        title="Folder Types",
        description="Folder types configuration",
    )

    task_types: list[TaskType] = Field(
        default=default_task_types,
        title="Task Types",
        description="Task types configuration",
    )

    statuses: list[Status] = Field(
        default=default_statuses,
        title="Statuses",
        description="Statuses configuration",
    )

    class Config:
        title = "Project anatomy"

    @validator("roots", "folder_types", "task_types")
    def ensure_unique_names(cls, value):
        ensure_unique_names(value)
        return value
