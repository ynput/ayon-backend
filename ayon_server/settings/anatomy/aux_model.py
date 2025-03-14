"""
Base aux model is used for anatomy items stored in project aux tables.

Namely:
    Folder types
    Task types
    Statuses
    Tags

Link types are slightly different, so they don't use this base model.
"""

from pydantic import validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class BaseAuxModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(..., title="Name", min_length=1, max_length=100)
    original_name: str | None = SettingsField(None, title="Original name", scope=[])

    def __hash__(self):
        return hash(self.name)

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v
