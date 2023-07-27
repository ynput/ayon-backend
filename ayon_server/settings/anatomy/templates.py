from pydantic import Field, validator

from ayon_server.settings.common import BaseSettingsModel
from ayon_server.settings.validators import ensure_unique_names, normalize_name


class BaseTemplate(BaseSettingsModel):
    name: str = Field(..., title="Name")

    @validator("name")
    def validate_name(cls, value):
        return normalize_name(value)


class WorkTemplate(BaseTemplate):
    directory: str = Field(..., title="Directory template")
    file: str = Field(..., title="File name template")


class PublishTemplate(BaseTemplate):
    directory: str = Field(..., title="Directory template")
    file: str = Field(..., title="File name template")


class HeroTemplate(BaseTemplate):
    directory: str = Field(..., title="Directory template")
    file: str = Field(..., title="File name template")


class DeliveryTemplate(BaseTemplate):
    directory: str = Field(..., title="Directory template")
    file: str = Field(..., title="File name template")


class CustomTemplate(BaseTemplate):
    _layout: str = "compact"
    value: str = Field("", title="Template value")


class StagingDirectory(BaseTemplate):
    _layout: str = "compact"
    directory: str = Field("")


# TODO: Custom templates are not supported yet
# data: dict[str, str] = Field(default_factory=dict)


class Templates(BaseSettingsModel):
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

    work: list[WorkTemplate] = Field(
        default_factory=lambda: [
            WorkTemplate(
                name="default",
                directory="{root[work]}/{project[name]}/{hierarchy}/{folder[name]}/work/{task[name]}",  # noqa: E501
                file="{project[code]}_{folder[name]}_{task[name]}_{@version}<_{comment}>.{ext}",  # noqa: E501
            ),
            WorkTemplate(
                name="unreal",
                directory="{root[work]}/{project[name]}/unreal/{task[name]}",
                file="{project[code]}_{asset}.{ext}",
            ),
        ],
        title="Work",
    )

    publish: list[PublishTemplate] = Field(
        title="Publish",
        default_factory=lambda: [
            PublishTemplate(
                name="default",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}/{product[name]}/{@version}",
                file="{project[code]}_{asset}_{product[name]}_{@version}<_{output}><.{@frame}><_{udim}>.{ext}",
            ),
            PublishTemplate(
                name="render",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}/{product[name]}/{@version}",
                file="{project[code]}_{asset}_{product[name]}_{@version}<_{output}><.{@frame}>.{ext}",
            ),
            PublishTemplate(
                name="online",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}/{product[name]}/{@version}",
                file="{originalBasename}<.{@frame}><_{udim}>.{ext}",
            ),
            PublishTemplate(
                name="source",
                directory="{root[work]}/{originalDirname}",
                file="{originalBasename}.{ext}",
            ),
            PublishTemplate(
                name="maya2unreal",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}",
                file="{product[name]}_{@version}<_{output}><.{@frame}>.{ext}",
            ),
            PublishTemplate(
                name="simpleUnrealTextureHero",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}/hero",
                file="{originalBasename}.{ext}",
            ),
            PublishTemplate(
                name="simpleUnrealTexture",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{product[type]}/{@version}",
                file="{originalBasename}_{@version}.{ext}",
            ),
        ],
    )

    hero: list[HeroTemplate] = Field(
        title="Hero",
        default_factory=lambda: [
            HeroTemplate(
                name="default",
                directory="{root[work]}/{project[name]}/{hierarchy}/{folder[name]}/publish/{product[type]}/{product[name]}/hero",  # noqa: E501
                file="{project[code]}_{folder[name]}_{task[name]}_hero<_{comment}>.{ext}",  # noqa: E501
            )
        ],
    )

    delivery: list[DeliveryTemplate] = Field(
        default_factory=list,
        title="Delivery",
    )

    others: list[CustomTemplate] = Field(
        default_factory=list,
        title="Others",
    )

    staging_directories: list[StagingDirectory] = Field(
        default_factory=list,
        title="Staging directories",
    )

    @validator("work", "publish", "hero", "delivery", "others", "staging_directories")
    def validate_template_group(cls, value):
        ensure_unique_names(value)
        return value

    @validator("work", "publish", "hero")
    def validate_has_default(cls, value):
        for template in value:
            if template.name == "default":
                break
        else:
            raise ValueError("Default template must be defined")
        return value
