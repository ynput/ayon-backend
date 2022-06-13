from pydantic import Field

from openpype.addons import BaseServerAddon
from openpype.settings.common import BaseSettingsModel


class TestSystemSettings(BaseSettingsModel):
    """Ftrack system settings."""

    field1: str = Field("alpha", title="Field 1")
    field2: str = Field("beta", title="Field 2")
    field3: str = Field("gamma", title="Field 3")


class AddOn(BaseServerAddon):
    version = "2.0.1"
    settings = TestSystemSettings
