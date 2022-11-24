from pydantic import Field, validator

from openpype.settings.common import (
    BaseSettingsModel,
    ensure_unique_names,
    normalize_name,
)


class BaseTemplate(BaseSettingsModel):
    name: str = Field(..., title="Template name")

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
    pass


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
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/work/{task[name]}",  # noqa: E501
                file="{project[code]}_{asset}_{task[name]}_{@version}<_{comment}>.{ext}",  # noqa: E501
            )
        ],
        title="Work",
    )

    publish: list[PublishTemplate] = Field(
        title="Publish",
        default_factory=lambda: [
            PublishTemplate(
                name="default",
                file="{project[code]}_{asset}_{subset}_{@version}<_{output}><.{@frame}><_{udim}>.{ext}",  # noqa: E501
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{family}/{subset}/{@version}",  # noqa: E501
            )
        ],
    )

    hero: list[HeroTemplate] = Field(
        title="Hero",
        default_factory=lambda: [
            HeroTemplate(
                name="default",
                directory="{root[work]}/{project[name]}/{hierarchy}/{asset}/publish/{family}/{subset}/hero",  # noqa: E501
                file="{project[code]}_{asset}_{task[name]}_hero<_{comment}>.{ext}",  # noqa: E501
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

    @validator("work", "publish", "hero", "delivery", "others")
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
