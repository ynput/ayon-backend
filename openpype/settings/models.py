from openpype.settings import Field
from openpype.settings.common import BaseSettingsModel
from openpype.settings.enum import task_types_enum


class PathModel(BaseSettingsModel):
    windows: str = Field("", title="Windows")
    macos: str = Field("", title="MacOS")
    linux: str = Field("", title="Linux")


class CustomTemplateModel(BaseSettingsModel):
    _layout = "expanded"
    _isGroup = True
    task_types: list[str] = Field(
        default_factory=list, title="Task types", enum_resolver=task_types_enum
    )

    # label:
    # Absolute path to workfile template or OpenPype Anatomy text is accepted.

    path: PathModel = Field(default_factory=PathModel, title="Path")


class ContextModel(BaseSettingsModel):
    _layout = "expanded"

    subsset_name_filter: list[str] = Field(
        default_factory=list, title="Subset name filters"
    )
    families: list[str] = Field(default_factory=list, title="Families")
    repre_names: list[str] = Field(default_factory=list, title="Repre names")
    loaders: list[str] = Field(default_factory=list, title="Loaders")


class ProfileModel(BaseSettingsModel):
    task_types: list[str] = Field(
        default_factory=list, title="Task types", enum_resolver=task_types_enum
    )

    tasks: list[str] = Field(default_factory=list, title="Task names")

    current_context: list[ContextModel] = Field(
        default_factory=list, title="""**Current context**"""
    )

    linked_assets: list[ContextModel] = Field(
        default_factory=list, title="""**Linked Assets/Shots**"""
    )


class TemplateWorkfileOptions(BaseSettingsModel):
    create_first_version: bool = Field(
        False,
        title="Create first workfile",
    )
    custom_templates: list[CustomTemplateModel] = Field(
        default_factory=list,
        title="Custom templates",
    )
    builder_on_start: bool = Field(False, title="Run Builder Profiles on first launch")
    profiles: list[ProfileModel] = Field(
        default_factory=list,
        title="Profiles",
    )
