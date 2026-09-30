"""
Base aux model is used for anatomy items stored in project aux tables.

Namely:
    Folder types
    Task types
    Statuses
    Tags

Link types are slightly different, so they don't use this base model.
"""

from pydantic import ValidationInfo, field_validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class BaseAuxModel(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(..., title="Name", min_length=1, max_length=100)
    # Used for renaming. Defaults to the name (validate_default), so clients
    # sending the anatomy back keep the original name of each item.
    original_name: str | None = SettingsField(
        None,
        title="Original name",
        scope=[],
        validate_default=True,
    )

    def __hash__(self):
        return hash(self.name)

    @field_validator("original_name")
    @classmethod
    def validate_original_name(cls, v, info: ValidationInfo):
        if v is None:
            # name is missing when it failed validation
            return info.data.get("name")
        return v
