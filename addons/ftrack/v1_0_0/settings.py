from pydantic import Field

from openpype.settings import BaseSettingsModel


class FtrackSettings(BaseSettingsModel):
    """Ftrack system settings."""

    server: str = Field("https://api.ftrack.com", title="ftrack server url")
    backup_server: str = Field("https://api.ftrack.com", title="backup server url")
    cost_limit: int = Field(10000, title="ftrack cost limit")
    api_key: str = Field("", title="ftrack api key")
