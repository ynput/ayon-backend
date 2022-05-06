from pydantic import BaseModel, Field


class TaskType(BaseModel):
    name: str = Field(..., title="Name", min_length=1, max_length=100)
    short_name: str = Field("", title="Short name")
    icon: str = Field("", title="Icon")


default_task_types = [
    TaskType(name="Generic", short_name="gener", icon="fa-question-circle"),
    TaskType(name="Art", short_name="art", icon="fa-paint-brush"),
    TaskType(name="Modeling", short_name="mdl", icon="fa-cube"),
    TaskType(name="Texture", short_name="tex", icon="fa-image"),
    TaskType(name="Lookdev", short_name="look", icon="fa-eye"),
    TaskType(name="Rigging", short_name="rig", icon="fa-user-md"),
    TaskType(name="Edit", short_name="edit", icon="fa-pencil-alt"),
    TaskType(name="Layout", short_name="lay", icon="fa-th-large"),
    TaskType(name="Setdress", short_name="dress", icon="fa-tshirt"),
    TaskType(name="Animation", short_name="anim", icon="fa-film"),
    TaskType(name="FX", short_name="fx", icon="fa-magic"),
    TaskType(name="Lighting", short_name="lgt", icon="fa-lightbulb"),
    TaskType(name="Paint", short_name="paint", icon="fa-paint-brush"),
    TaskType(name="Compositing", short_name="comp", icon="fa-images"),
]
