from pydantic import Field

from ayon_server.settings.common import BaseSettingsModel


class TaskType(BaseSettingsModel):
    _layout: str = "compact"
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    shortName: str = Field("", title="Short name")
    icon: str = Field("", title="Icon", widget="icon")
    original_name: str | None = Field(
        None,
        title="Original name",
        scope=[],
    )  # Used for renaming


default_task_types = [
    TaskType(name="Generic", shortName="gener", icon="task_alt"),
    TaskType(name="Art", shortName="art", icon="palette"),
    TaskType(name="Modeling", shortName="mdl", icon="language"),
    TaskType(name="Texture", shortName="tex", icon="brush"),
    TaskType(name="Lookdev", shortName="look", icon="ev_shadow"),
    TaskType(name="Rigging", shortName="rig", icon="construction"),
    TaskType(name="Edit", shortName="edit", icon="imagesearch_roller"),
    TaskType(name="Layout", shortName="lay", icon="nature_people"),
    TaskType(name="Setdress", shortName="dress", icon="scene"),
    TaskType(name="Animation", shortName="anim", icon="directions_run"),
    TaskType(name="FX", shortName="fx", icon="fireplace"),
    TaskType(name="Lighting", shortName="lgt", icon="highlight"),
    TaskType(name="Paint", shortName="paint", icon="video_stable"),
    TaskType(name="Compositing", shortName="comp", icon="layers"),
    TaskType(name="Roto", shortName="roto", icon="gesture"),
    TaskType(name="Matchmove", shortName="matchmove", icon="switch_video"),
]
