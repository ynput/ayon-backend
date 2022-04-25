from pydantic import BaseModel, Field, conset

from openpype.entities import ProjectEntity

from anatomy.roots import Root, default_roots
from anatomy.templates import Templates
from anatomy.task_types import TaskType, default_task_types
from anatomy.folder_types import FolderType, default_folder_types


Attributes = ProjectEntity.model.attrib_model


class AnatomyTemplate(BaseModel):
    roots: conset(Root, min_items=1) = Field(
        default=default_roots,
        title="Roots",
    )

    templates: Templates = Field(
        default_factory=Templates,
        title="Templates",
    )

    attributes: Attributes = Field(
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
        title = "Project Template"
