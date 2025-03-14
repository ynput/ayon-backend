from ayon_server.settings.settings_field import SettingsField

from .aux_model import BaseAuxModel


class TaskType(BaseAuxModel):
    shortName: str = SettingsField("", title="Short name")
    color: str = SettingsField("#cccccc", title="Color", widget="color")
    icon: str = SettingsField("task_alt", title="Icon", widget="icon")


default_task_types = [
    TaskType(name="Generic", shortName="gener", icon="task_alt", color="#5c6c79"),
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
