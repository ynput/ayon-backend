from typing import get_args

from pydantic import validator

from ayon_server.entities.project_aux_tables import State
from ayon_server.settings.settings_field import SettingsField
from ayon_server.types import ProjectLevelEntityType

from .aux_model import BaseAuxModel


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


def get_default_scopes():
    return get_args(ProjectLevelEntityType)


class Status(BaseAuxModel):
    shortName: str = SettingsField(
        "",
        title="Short name",
        example="PRG",
    )
    state: State = SettingsField(
        "not_started",
        title="State",
        enum_resolver=get_state_enum,
        example="in_progress",
    )
    icon: str = SettingsField(
        "",
        title="Icon",
        widget="icon",
        example="play_arrow",
    )
    color: str = SettingsField(
        "#cacaca",
        title="Color",
        widget="color",
        example="#3498db",
    )
    scope: list[str] | None = SettingsField(
        default_factory=get_default_scopes,
        example=get_default_scopes(),
        enum_resolver=scope_enum,
        description="Limit the status to specific entity types.",
    )
    original_name: str | None = SettingsField(
        None,
        scope=[],
        example=None,
    )  # Used for renaming, we don't show it in the UI

    @validator("scope")
    def validate_scope(cls, v, values):
        if v is None:
            return get_default_scopes()
        return v


default_statuses = [
    Status(
        name="Not ready",
        shortName="NRD",
        icon="fiber_new",
        color="#3d444f",
        state="not_started",
        scope=["folder", "product", "task"],
    ),
    Status(
        name="Ready to start",
        shortName="RDY",
        icon="timer",
        color="#bababa",
        state="not_started",
        scope=["folder", "task"],
    ),
    Status(
        name="In progress",
        shortName="PRG",
        icon="play_arrow",
        color="#5bb8f5",
        state="in_progress",
        scope=["folder", "task"],
    ),
    Status(
        name="Pending review",
        shortName="RVW",
        icon="visibility",
        color="#ffcd19",
        state="in_progress",
        scope=["folder", "version", "task"],
    ),
    Status(
        name="Approved",
        shortName="APP",
        icon="task_alt",
        color="#08f094",
        state="done",
        scope=["folder", "product", "version", "task"],
    ),
    Status(
        name="On hold",
        shortName="HLD",
        icon="back_hand",
        color="#fa6e46",
        state="blocked",
        scope=["folder", "task"],
    ),
    Status(
        name="Omitted",
        shortName="OMT",
        icon="block",
        color="#cb1a1a",
        state="blocked",
        scope=["folder", "product", "version", "representation", "task"],
    ),
]
