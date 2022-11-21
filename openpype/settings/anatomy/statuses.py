from typing import Literal
from pydantic import Field

from openpype.settings.common import BaseSettingsModel


State = Literal["not_started", "in_progress", "done", "blocked"]


def get_state_enum():
    return [
        {"value": "not_started", "label": "Not Started"},
        {"value": "in_progress", "label": "In Progress"},
        {"value": "done", "label": "Done"},
        {"value": "blocked", "label": "Blocked"},
    ]


class Status(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    color: str = Field("#cacaca", title="Color", widget="color")
    state: State = Field("not_started", title="State", enum_resolver=get_state_enum)
    original_name: str | None = Field(None, scope="hidden")  # Used for renaming

    def __hash__(self):
        return hash(self.name)


default_statuses = [
    Status(name="Not ready", color="#cacaca", state="not_started"),
    Status(name="Ready to start", color="#cc99ff", state="not_started"),
    Status(name="In progress", color="#3498db", state="in_progress"),
    Status(name="Pending review", color="#f1c40f", state="in_progress"),
    Status(name="Approved", color="#1cbc90", state="done"),
    Status(name="On hold", color="#e74c3c", state="blocked"),
    Status(name="Omitted", color="#0099ff", state="blocked"),
]
