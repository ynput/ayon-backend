from typing import Literal

from pydantic import Field

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.types import ProjectLevelEntityType


class LinkType(BaseSettingsModel):
    _layout: str = "compact"
    link_type: str = Field(..., title="Link type", min_length=1, max_length=100)
    input_type: ProjectLevelEntityType = Field(..., title="Input type")
    output_type: ProjectLevelEntityType = Field(..., title="Output type")
    color: str | None = Field(None, title="Color", widget="color")
    style: Literal["solid", "dashed"] = Field("solid", title="Style")

    def __hash__(self):
        return hash(self.name)


default_link_types = [
    LinkType(
        link_type="generative",
        input_type="version",
        output_type="version",
        color="#2626e0",
    ),
    LinkType(
        link_type="breakdown",
        input_type="folder",
        output_type="folder",
        color="#27792a",
    ),
    LinkType(
        link_type="reference",
        input_type="version",
        output_type="version",
        color="#d94383",
    ),
    LinkType(
        link_type="template",
        input_type="folder",
        output_type="folder",
        color="#d94383",
    ),
]
