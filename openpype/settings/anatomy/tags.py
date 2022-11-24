from pydantic import Field

from openpype.settings.common import BaseSettingsModel


class Tag(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    color: str = Field("#cacaca", title="Color", widget="color")
    original_name: str | None = Field(None, scope="hidden")  # Used for renaming

    def __hash__(self):
        return hash(self.name)

