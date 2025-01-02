from pydantic import validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.settings_field import SettingsField


class TaskType(BaseSettingsModel):
    _layout = "compact"
    name: str = SettingsField(..., title="Name", min_length=1, max_length=100)
    shortName: str = SettingsField("", title="Short name")
    color: str = SettingsField("#cccccc", title="Color", widget="color")
    icon: str = SettingsField("task_alt", title="Icon", widget="icon")

    # Set to old name when renaming
    original_name: str | None = SettingsField(None, title="Original name", scope=[])

    def __hash__(self):
        return hash(self.name)

    @validator("original_name")
    def validate_original_name(cls, v, values):
        if v is None:
            return values["name"]
        return v


default_task_types = [
    TaskType(name="Generic", shortName="gener", icon="task_alt", color="#585858"),
    TaskType(name="Art", shortName="art", icon="palette", color="#BC3333"),
    TaskType(name="Modeling", shortName="mdl", icon="language", color="#E74C4C"),
    TaskType(name="Texture", shortName="tex", icon="brush", color="#D84444"),
    TaskType(name="Lookdev", shortName="look", icon="ev_shadow", color="#44944A"),
    TaskType(name="Rigging", shortName="rig", icon="construction", color="#1AAFC3"),
    TaskType(name="Edit", shortName="edit", icon="imagesearch_roller", color="#313894"),
    TaskType(name="Layout", shortName="lay", icon="nature_people", color="#2359B3"),
    TaskType(name="Setdress", shortName="dress", icon="scene", color="#1A655C"),
    TaskType(
        name="Animation", shortName="anim", icon="directions_run", color="#3599F1"
    ),
    TaskType(name="FX", shortName="fx", icon="fireplace", color="#A43BC1"),
    TaskType(name="Lighting", shortName="lgt", icon="highlight", color="#812DB1"),
    TaskType(name="Paint", shortName="paint", icon="video_stable", color="#317537"),
    TaskType(name="Compositing", shortName="comp", icon="layers", color="#612BA3"),
    TaskType(name="Roto", shortName="roto", icon="gesture", color="#1C70B2"),
    TaskType(
        name="Matchmove", shortName="matchmove", icon="switch_video", color="#1A777B"
    ),
]
