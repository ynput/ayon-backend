from pydantic import Field

from openpype.settings.common import BaseSettingsModel


class Root(BaseSettingsModel):
    """Setup root paths"""

    _layout: str = "compact"

    name: str = Field(
        ...,
        title="Root name",
        regex="^[a-zA-Z0-9_]{1,}$",
    )

    windows: str = Field(
        "",
        title="Windows",
    )

    linux: str = Field(
        "",
        title="Linux",
    )

    darwin: str = Field(
        "",
        title="Darwin",
    )


default_roots = [
    Root(
        name="work",
        windows="C:/projects",
        linux="/mnt/share/projects",
        darwin="/Volumes/projects",
    )
]
