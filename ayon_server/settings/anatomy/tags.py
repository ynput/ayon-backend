from pydantic import validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class Tag(BaseSettingsModel):
    _layout: str = "compact"
    name: str = SettingsField(
        ..., title="Name", min_length=1, max_length=100, example="fluffy"
    )
    color: str = SettingsField(
        "#cacaca", title="Color", widget="color", example="#3498db"
    )
    original_name: str | None = SettingsField(None, scope=[])  # Used for renaming

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v

    def __hash__(self):
        return hash(self.name)
