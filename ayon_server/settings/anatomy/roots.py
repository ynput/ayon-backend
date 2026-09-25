from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class Root(BaseSettingsModel):
    """Setup root paths"""

    _layout = "expanded"

    name: str = SettingsField(
        ...,
        title="Root name",
        regex="^[a-zA-Z0-9_]{1,}$",
        example="work",
    )

    windows: str = SettingsField(
        "",
        title="Windows",
        example="C:/projects",
    )

    linux: str = SettingsField(
        "",
        title="Linux",
        example="/mnt/share/projects",
    )

    darwin: str = SettingsField(
        "",
        title="Darwin",
        example="/Volumes/projects",
    )


default_roots = [
    Root(
        name="work",
        windows="C:/projects",
        linux="/mnt/share/projects",
        darwin="/Volumes/projects",
    )
]
