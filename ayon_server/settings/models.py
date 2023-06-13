from pydantic import validator

from ayon_server.settings import Field
from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.enum import task_types_enum
from ayon_server.settings.validators import ensure_unique_names


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
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum
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


# --- Host 'imageio' models ---
class ImageIOConfigModel(BaseSettingsModel):
    override_global_config: bool = Field(
        False,
        title="Override global OCIO config"
    )
    filepath: list[str] = Field(
        default_factory=list,
        title="Config path"
    )


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = Field("", title="Rule name")
    pattern: str = Field("", title="Regex pattern")
    colorspace: str = Field("", title="Colorspace name")
    ext: str = Field("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = Field(False)
    rules: list[ImageIOFileRuleModel] = Field(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class ImageIORemappingRulesModel(BaseSettingsModel):
    host_native_name: str = Field(
        title="Application native colorspace name"
    )
    ocio_name: str = Field(title="OCIO colorspace name")


class ImageIORemappingModel(BaseSettingsModel):
    rules: list[ImageIORemappingRulesModel] = Field(
        default_factory=list)


# Base model that can be used as is if host does not need any custom fields
class HostImageIOBaseModel(BaseSettingsModel):
    activate_host_color_management: bool = Field(
        True, title="Enable Color Management"
    )
    ocio_config: ImageIOConfigModel = Field(
        default_factory=ImageIOConfigModel,
        title="OCIO config"
    )
    file_rules: ImageIOFileRulesModel = Field(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )


class HostImageIORemappedModel(BaseSettingsModel):
    activate_host_color_management: bool = Field(
        True, title="Enable Color Management"
    )
    remapping: ImageIORemappingModel = Field(
        title="Remapping colorspace names",
        default_factory=ImageIORemappingModel
    )
    ocio_config: ImageIOConfigModel = Field(
        default_factory=ImageIOConfigModel,
        title="OCIO config"
    )
    file_rules: ImageIOFileRulesModel = Field(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )

# Backwards compatibility
ImageIOBaseModel = HostImageIOBaseModel
