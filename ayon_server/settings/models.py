from ayon_server.settings import Field
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.enum import task_types_enum


class MultiplatformPathModel(BaseSettingsModel):
    windows: str = Field("", title="Windows")
    linux: str = Field("", title="Linux")
    darwin: str = Field("", title="MacOS")


class MultiplatformPathListModel(BaseSettingsModel):
    windows: list[str] = Field(default_factory=list, title="Windows")
    linux: list[str] = Field(default_factory=list, title="Linux")
    darwin: list[str] = Field(default_factory=list, title="MacOS")


class CustomTemplateModel(BaseSettingsModel):
    _layout = "expanded"
    _isGroup = True
    task_types: list[str] = Field(
        default_factory=list, title="Task types", enum_resolver=task_types_enum
    )

    # label:
    # Absolute path to workfile template or Ayon Anatomy text is accepted.

    path: MultiplatformPathModel = Field(
        default_factory=MultiplatformPathModel, title="Path"
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


