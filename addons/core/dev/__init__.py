from pydantic import Field

from openpype.addons import BaseServerAddon
from openpype.settings import BaseSettingsModel


class CoreSettings(BaseSettingsModel):
    studio_name: str = Field("", title="Studio name")
    artist_count: int = Field(0, title="Artist count")


class CoreAddon(BaseServerAddon):
    name = "core"
    version = "1.0.0"
    settings_model = CoreSettings
