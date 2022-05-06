from pydantic import BaseModel, Field, validator

from openpype.anatomy.folder_types import FolderType, default_folder_types
from openpype.anatomy.roots import Root, default_roots
from openpype.anatomy.task_types import TaskType, default_task_types
from openpype.anatomy.templates import Templates
from openpype.anatomy.validators import ensure_unique_names
from openpype.entities import ProjectEntity


Attributes = ProjectEntity.model.attrib_model


class Anatomy(BaseModel):
    roots: list[Root] = Field(
        default=default_roots,
        title="Roots",
    )

    templates: Templates = Field(
        default_factory=Templates,
        title="Templates",
    )

    attributes: Attributes = Field(  # type: ignore
        default_factory=Attributes,
        title="Attributes",
    )

    folder_types: list[FolderType] = Field(
        default=default_folder_types,
        title="Folder Types",
    )

    task_types: list[TaskType] = Field(
        default=default_task_types,
        title="Task Types",
    )

    class Config:
        title = "Project anatomy"

    @validator("roots", "folder_types", "task_types")
    def ensure_unique_names(cls, value):
        ensure_unique_names(value)
        return value
