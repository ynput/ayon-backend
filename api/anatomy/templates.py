from typing import Iterable, Any
from nxtools import slugify
from pydantic import BaseModel, Field, conset, validator


def normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Name must not be empty")
    components = slugify(name).split("-")
    return components[0] + "".join(x.title() for x in components[1:])


def ensure_unique_names(objects: Iterable[Any]) -> None:
    names = []
    for obj in objects:
        if not hasattr(obj, "name"):
            raise ValueError("Object without name provided")
        if obj.name not in names:
            names.append(obj.name)
        else:
            raise ValueError(f"Duplicate name {obj.name}]")


class BaseTemplate(BaseModel):
    name: str = Field(..., title="Template name")

    @validator("name")
    def validate_name(cls, value):
        return normalize_name(value)


class WorkTemplate(BaseTemplate):
    directory: str = Field(
        "{root[work]}/{project[name]}/{hierarchy}/{asset}/work/{task[name]}",
        title="Directory template",
    )
    file: str = Field(
        "{project[code]}_{asset}_{task[name]}_{@version}<_{comment}>.{ext}",
        title="File name template",
    )


class RenderTemplate(BaseTemplate):
    directory: str = Field(
        "{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{family}/{subset}/{@version}",  # noqa
        title="Directory template",
    )
    file: str = Field(
        "{project[code]}_{asset}_{subset}_{@version}<_{output}><.{@frame}>.{ext}",  # noqa
        title="File name template",
    )


class PublishTemplate(BaseTemplate):
    directory: str = Field(
        "{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{family}/{subset}/{@version}",  # noqa
        title="Directory template",
    )
    file: str = Field(
        "{project[code]}_{asset}_{subset}_{@version}<_{output}><.{@frame}><_{udim}>.{ext}",  # noqa
        title="File name template",
    )


class HeroTemplate(BaseTemplate):
    directory: str = Field(
        "{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{family}/{subset}/hero",  # noqa
        title="Directory template",
    )
    file: str = Field(
        "{project[code]}_{asset}_{subset}_hero<_{output}><.{frame}>.{ext}",
        title="File name template",
    )


class DeliveryTemplate(BaseTemplate):
    path: str = Field("", title="Path template")


class CustomTemplate(BaseTemplate):
    data: dict[str, str] = Field(default_factory=dict)


class Templates(BaseModel):
    version_padding: int = Field(
        default=3,
        title="Version padding",
        gt=0,
    )

    version: str = Field(
        default="v{version:0>{@version_padding}}",
        title="Version template",
    )

    frame_padding: int = Field(
        default=4,
        title="Frame padding",
        gt=0,
    )

    frame: str = Field(
        default="{frame:0>{@frame_padding}}",
        title="Frame template",
    )

    work: conset(WorkTemplate, min_items=1) = Field(
        default_factory=lambda: [WorkTemplate(name="default")],
        title="Work",
    )

    render: conset(RenderTemplate, min_items=1) = Field(
        default_factory=lambda: [RenderTemplate(name="default")],
        title="Render",
    )

    publish: conset(PublishTemplate, min_items=1) = Field(
        default_factory=lambda: [PublishTemplate(name="default")],
        title="Publish",
    )

    hero: list[HeroTemplate] = Field(
        default_factory=lambda: [HeroTemplate(name="default")],
        title="Hero",
    )

    delivery: list[DeliveryTemplate] = Field(
        default_factory=list,
        title="Delivery",
    )

    others: list[CustomTemplate] = Field(
        default_factory=list,
        title="Others",
    )

    @validator("work", "publish", "hero", "delivery", "others")
    def validate_template_group(cls, value):
        ensure_unique_names(value)
        return value
