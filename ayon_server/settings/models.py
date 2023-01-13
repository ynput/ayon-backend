from ayon_server.settings import Field
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.enum import task_types_enum


class MultiplatformPathModel(BaseSettingsModel):
    windows: str = Field("", title="Windows")
    macos: str = Field("", title="MacOS")
    linux: str = Field("", title="Linux")


class MultiplatformPathListModel(BaseSettingsModel):
    windows: list[str] = Field(default_factory=list, title="Windows")
    macos: list[str] = Field(default_factory=list, title="MacOS")
    linux: list[str] = Field(default_factory=list, title="Linux")


class CustomTemplateModel(BaseSettingsModel):
    _layout = "expanded"
    _isGroup = True
    task_types: list[str] = Field(
        default_factory=list, title="Task types", enum_resolver=task_types_enum
    )

    # label:
    # Absolute path to workfile template or Ayon Anatomy text is accepted.

    path: MultiplatformPathModel = Field(
        default_factory=MultiplatformPathModel,
        title="Path"
    )


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


class TemplateWorkfileBaseOptions(BaseSettingsModel):
    create_first_version: bool = Field(
        False,
        title="Create first workfile",
    )
    custom_templates: list[CustomTemplateModel] = Field(
        default_factory=list,
        title="Custom templates",
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
