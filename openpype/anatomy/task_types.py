from pydantic import BaseModel, Field


class TaskType(BaseModel):
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    short_name: str = Field("", title="Short name")
    icon: str = Field("", title="Icon")


default_task_types = [
    TaskType(name="Generic", short_name="gener", icon="task_alt"),
    TaskType(name="Art", short_name="art", icon="palette"),
    TaskType(name="Modeling", short_name="mdl", icon="language"),
    TaskType(name="Texture", short_name="tex", icon="brush"),
    TaskType(name="Lookdev", short_name="look", icon="ev_shadow"),
    TaskType(name="Rigging", short_name="rig", icon="construction"),
    TaskType(name="Edit", short_name="edit", icon="imagesearch_roller"),
    TaskType(name="Layout", short_name="lay", icon="nature_people"),
    TaskType(name="Setdress", short_name="dress", icon="scene"),
    TaskType(name="Animation", short_name="anim", icon="directions_run"),
    TaskType(name="FX", short_name="fx", icon="fireplace"),
    TaskType(name="Lighting", short_name="lgt", icon="highlight"),
    TaskType(name="Paint", short_name="paint", icon="video_stable"),
    TaskType(name="Compositing", short_name="comp", icon="layers"),
    TaskType(name="Roto", short_name="roto", icon="gesture"),
]
