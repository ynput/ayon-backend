from pydantic import Field

from openpype.addons import BaseServerAddon
from openpype.settings.common import BaseSettingsModel


class TestSystemSettings(BaseSettingsModel):
    """Ftrack system settings."""

    field1: str = Field("alpha", title="Field 1")
    field2: str = Field("beta", title="Field 2")


class AddOn(BaseServerAddon):
    version = "2.0.0"
    settings = TestSystemSettings
