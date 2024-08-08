from pydantic import validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.enum import task_types_enum
from ayon_server.settings.settings_field import SettingsField
from ayon_server.settings.validators import ensure_unique_names


class MultiplatformPathModel(BaseSettingsModel):
    windows: str = SettingsField("", title="Windows")
    linux: str = SettingsField("", title="Linux")
    darwin: str = SettingsField("", title="MacOS")


class MultiplatformPathListModel(BaseSettingsModel):
    windows: list[str] = SettingsField(default_factory=list, title="Windows")
    linux: list[str] = SettingsField(default_factory=list, title="Linux")
    darwin: list[str] = SettingsField(default_factory=list, title="MacOS")


class CustomTemplateModel(BaseSettingsModel):
    _layout = "expanded"
    _isGroup = True
    task_types: list[str] = SettingsField(
        default_factory=list, title="Task types", enum_resolver=task_types_enum
    )

    # label:
    # Absolute path to workfile template or Ayon Anatomy text is accepted.

    path: MultiplatformPathModel = SettingsField(
        default_factory=MultiplatformPathModel, title="Path"
    )


class TemplateWorkfileBaseOptions(BaseSettingsModel):
    create_first_version: bool = SettingsField(
        False,
        title="Create first workfile",
    )
    custom_templates: list[CustomTemplateModel] = SettingsField(
        default_factory=list,
        title="Custom templates",
    )


# --- Host 'imageio' models ---
class ImageIOConfigModel(BaseSettingsModel):
    enabled: bool = SettingsField(False)
    filepath: list[str] = SettingsField(default_factory=list, title="Config path")


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    enabled: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list, title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


# Base model that can be used as is if host does not need any custom fields
class ImageIOBaseModel(BaseSettingsModel):
    ocio_config: ImageIOConfigModel = SettingsField(
        default_factory=ImageIOConfigModel, title="OCIO config"
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel, title="File Rules"
    )
