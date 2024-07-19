from typing import Literal, get_args

from pydantic import Field, validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.types import ProjectLevelEntityType

State = Literal["not_started", "in_progress", "done", "blocked"]


def get_state_enum():
    return [
        {"value": "not_started", "label": "Not Started"},
        {"value": "in_progress", "label": "In Progress"},
        {"value": "done", "label": "Done"},
        {"value": "blocked", "label": "Blocked"},
    ]


def scope_enum() -> list[dict[str, str]]:
    return [
        {"value": v, "label": v.capitalize()} for v in get_args(ProjectLevelEntityType)
    ]


class Status(BaseSettingsModel):
    _layout: str = "compact"
    original_name: str | None = Field(
        None, scope=[]
    )  # Used for renaming, we don't show it in the UI
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    shortName: str = Field("", title="Short name")
    state: State = Field("not_started", title="State", enum_resolver=get_state_enum)
    icon: str = Field("", title="Icon", widget="icon")
    color: str = Field("#cacaca", title="Color", widget="color")
    scope: list[str] | None = Field(
        None,
        example=["task"],
        enum_resolver=scope_enum,
        description=(
            "Limit the status to specific entity types. "
            " If empty, the status is available for all entity types."
        ),
    )

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v

    @validator("scope")
    def validate_scope(cls, v, values):
        if v == []:
            return None
        return v

    def __hash__(self):
        return hash(self.name)


default_statuses = [
    Status(
        name="Not ready",
        shortName="NRD",
        icon="fiber_new",
        color="#434a56",
        state="not_started",
        scope=None,
    ),
    Status(
        name="Ready to start",
        shortName="RDY",
        icon="timer",
        color="#bababa",
        state="not_started",
        scope=None,
    ),
    Status(
        name="In progress",
        shortName="PRG",
        icon="play_arrow",
        color="#3498db",
        state="in_progress",
        scope=None,
    ),
    Status(
        name="Pending review",
        shortName="RVW",
        icon="visibility",
        color="#ff9b0a",
        state="in_progress",
        scope=None,
    ),
    Status(
        name="Approved",
        shortName="APP",
        icon="task_alt",
        color="#00f0b4",
        state="done",
        scope=None,
    ),
    Status(
        name="On hold",
        shortName="HLD",
        icon="back_hand",
        color="#fa6e46",
        state="blocked",
        scope=None,
    ),
    Status(
        name="Omitted",
        shortName="OMT",
        icon="block",
        color="#cb1a1a",
        state="blocked",
        scope=None,
    ),
]
