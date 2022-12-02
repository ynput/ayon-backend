import json
from pydantic import Field, validator
from openpype.settings import BaseSettingsModel
from openpype.exceptions import BadRequestException

from .publish_plugins import PublishPuginsModel, DEFAULT_PUBLISH_VALUES
from .tools import GlobalToolsModel, DEFAULT_TOOLS_VALUES


class MultiplatformStrList(BaseSettingsModel):
    windows: list[str] = Field(default_factory=list, title="Windows")
    linux: list[str] = Field(default_factory=list, title="Linux")
    darwin: list[str] = Field(default_factory=list, title="MacOS")


class CoreSettings(BaseSettingsModel):
    studio_name: str = Field("", title="Studio name")
    studio_code: str = Field("", title="Studio code")
    environments: str = Field("{}", widget="textarea")
    tools: GlobalToolsModel = Field(
        default_factory=GlobalToolsModel,
        title="Tools"
    )
    publish: PublishPuginsModel = Field(
        default_factory=PublishPuginsModel,
        title="Publish plugins"
    )
    project_plugins: MultiplatformStrList = Field(
        default_factory=MultiplatformStrList,
        title="Additional Project Plugin Paths",
    )
    project_folder_structure: str = Field(
        "{}",
        widget="textarea",
        title="Project folder structure",
        section="---"
    )
    project_environments: str = Field(
        "{}",
        widget="textarea",
        title="Project environments",
        section="---"
    )

    @validator(
        "environments",
        "project_folder_structure",
        "project_environments")
    def validate_json(cls, value):
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


DEFAULT_VALUES = {
    "studio_name": "",
    "studio_code": "",
    "environments": "{}",
    "tools": DEFAULT_TOOLS_VALUES,
    "publish": DEFAULT_PUBLISH_VALUES,
    "project_folder_structure": "{}",
    "project_plugins": {
        "windows": [],
        "darwin": [],
        "linux": []
    },
    "project_environments": "{}"
}