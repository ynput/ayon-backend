from typing import Literal

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField
from ayon_server.types import ProjectLevelEntityType


class LinkType(BaseSettingsModel):
    _layout = "compact"
    link_type: str = SettingsField(..., title="Link type", min_length=1, max_length=100)
    input_type: ProjectLevelEntityType = SettingsField(..., title="Input type")
    output_type: ProjectLevelEntityType = SettingsField(..., title="Output type")
    color: str | None = SettingsField(None, title="Color", widget="color")
    style: Literal["solid", "dashed"] = SettingsField("solid", title="Style")

    def __hash__(self):
        return hash((self.link_type, self.input_type, self.output_type))

    @property
    def name(self) -> str:
        return f"{self.link_type}|{self.input_type}|{self.output_type}"


default_link_types = [
    LinkType(
        link_type="generative",
        input_type="version",
        output_type="version",
        color="#3f67de",
        style="solid",
    ),
    LinkType(
        link_type="breakdown",
        input_type="folder",
        output_type="folder",
        color="#6edd72",
        style="solid",
    ),
    LinkType(
        link_type="reference",
        input_type="version",
        output_type="version",
        color="#d94383",
        style="solid",
    ),
    LinkType(
        link_type="template",
        input_type="folder",
        output_type="folder",
        color="#fff824",
        style="solid",
    ),
]
