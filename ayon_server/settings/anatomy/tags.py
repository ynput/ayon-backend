from pydantic import Field, validator

from ayon_server.settings.common import BaseSettingsModel


class Tag(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    color: str = Field("#cacaca", title="Color", widget="color")
    original_name: str | None = Field(None, scope=[])  # Used for renaming

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v

    def __hash__(self):
        return hash(self.name)
