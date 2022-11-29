import json
from pydantic import Field, validator

from openpype.settings import BaseSettingsModel, ensure_unique_names
from openpype.exceptions import BadRequestException


def validate_json_dict(value):
    if not value.strip():
        return "{}"
    try:
        converted_value = json.loads(value)
        success = isinstance(converted_value, dict)
    except json.JSONDecodeError:
        success = False

    if not success:
        raise BadRequestException(
            "Environment's can't be parsed as json object"
        )
    return value


class MultiplatformStrList(BaseSettingsModel):
    windows: list[str] = Field(default_factory=list, title="Windows")
    linux: list[str] = Field(default_factory=list, title="Linux")
    darwin: list[str] = Field(default_factory=list, title="MacOS")


class AppVariant(BaseSettingsModel):
    name: str = Field("", title="Name")
    label: str = Field("", title="Label")
    executables: MultiplatformStrList = Field(
        default_factory=MultiplatformStrList, title="Executables"
    )
    arguments: MultiplatformStrList = Field(
        default_factory=MultiplatformStrList, title="Arguments"
    )
    environment: str = Field("{}", title="Environment", widget="textarea")


class AppVariantWithPython(AppVariant):
    use_python_2: bool = Field(False, title="Use Python 2")


class AppGroup(BaseSettingsModel):
    enabled: bool = Field(True)
    label: str = Field("", title="Label")
    host_hame: str = Field("", title="Host name")
    icon: str = Field("", title="Icon")
    environment: str = Field("{}", title="Environment", widget="textarea")

    variants: list[AppVariant] = Field(
        default_factory=list,
        title="Variants",
        description="Different variants of the applications",
        section="Variants",
    )

    @validator("variants")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class AppGroupWithPython(AppGroup):
    variants: list[AppVariantWithPython] = Field(
        default_factory=list,
        title="Variants",
        description="Different variants of the applications",
        section="Variants",
    )


class AdditionalAppGroup(BaseSettingsModel):
    enabled: bool = Field(True)
    name: str = Field("", title="Name")
    label: str = Field("", title="Label")
    host_hame: str = Field("", title="Host name")
    icon: str = Field("", title="Icon")
    environment: str = Field("{}", title="Environment", widget="textarea")

    variants: list[AppVariantWithPython] = Field(
        default_factory=list,
        title="Variants",
        description="Different variants of the applications",
        section="Variants",
    )

    @validator("variants")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class ToolVariantModel(BaseSettingsModel):
    name: str = Field("", title="Name")
    label: str = Field("", title="Label")
    host_names: list[str] = Field(default_factory=list, title="Hosts")
    # TODO use applications enum if possible
    app_variants: list[str] = Field(default_factory=list, title="Applications")
    environment: str = Field("{}", title="Environments", widget="textarea")

    @validator("environment")
    def validate_json(cls, value):
        return validate_json_dict(value)


class ToolGroupModel(BaseSettingsModel):
    name: str = Field("", title="Name")
    label: str = Field("", title="Label")
    environment: str = Field("{}", title="Environments", widget="textarea")
    variants: list[ToolVariantModel] = Field(
        default_factory=ToolVariantModel
    )

    @validator("environment")
    def validate_json(cls, value):
        return validate_json_dict(value)

    @validator("variants")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class ApplicationsSettings(BaseSettingsModel):
    """Applications settings"""

    maya: AppGroupWithPython = Field(
        default_factory=AppGroupWithPython, title="Autodesk Maya")
    flame: AppGroupWithPython = Field(
        default_factory=AppGroupWithPython, title="Autodesk Flame")
    nuke: AppGroupWithPython = Field(
        default_factory=AppGroupWithPython, title="Nuke")
    aftereffects: AppGroup = Field(
        default_factory=AppGroupWithPython, title="Adobe After Effects")
    photoshop: AppGroup = Field(
        default_factory=AppGroupWithPython, title="Adobe Photoshop")
    tvpaint: AppGroup = Field(
        default_factory=AppGroupWithPython, title="TVPaint")
    harmony: AppGroup = Field(
        default_factory=AppGroupWithPython, title="Harmony")
    additional_apps: list[AdditionalAppGroup] = Field(
        default_factory=list, title="Additional Applications"
    )

    @validator("additional_apps")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value


class ApplicationsAddonSettings(BaseSettingsModel):
    applications: ApplicationsSettings = Field(
        default_factory=ApplicationsSettings,
        title="Applications"
    )
    tool_groups: list[ToolGroupModel] = Field(default_factory=list)

    @validator("tool_groups")
    def validate_unique_name(cls, value):
        ensure_unique_names(value)
        return value
