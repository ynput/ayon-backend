from pydantic import Field

from openpype.settings.common import BaseSettingsModel


class Status(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    icon: str = Field("view_kanban", title="Icon")
    color: str = Field("#c0b0d0", title="Color")
    original_name: str | None = Field(None, scope="hidden")  # Used for renaming

    def __hash__(self):
        return hash(self.name)


default_statuses = [
    Status(name="Unknown"),
]
