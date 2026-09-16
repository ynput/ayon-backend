from typing import Annotated, Any

from pydantic import validator

from ayon_server.types import Field, OPModel, SimpleValue
from ayon_server.utils import slugify

from .icon_model import IconModel


class EnumItem(OPModel):
    """Attribute enum item.

    Lives under `ayon_server.models` (rather than `ayon_server.enum`, which
    is where it's re-exported from) because `ayon_server.forms` also needs
    it for select/multiselect options, and `ayon_server.enum` itself
    depends on `ayon_server.forms` - keeping the model in a dependency-free
    leaf module avoids a cycle between the two.
    """

    value: Annotated[
        SimpleValue,
        Field(title="Enum value", example="my_value"),
    ]

    label: Annotated[
        str,
        Field(title="Enum label", example="My Value"),
    ]

    description: Annotated[
        str | None,
        Field(title="Enum item description", example="Description of My value"),
    ] = None

    fulltext: Annotated[
        list[str] | None,
        Field(title="Fulltext search terms", example=["my", "value"]),
    ] = None

    group: Annotated[
        str | None,
        Field(
            title="Enum group",
            example=None,
        ),
    ] = None

    icon: Annotated[
        str | IconModel | None,
        Field(
            title="Icon",
            description="Icon name (material symbol) or IconModel object",
            example="dashboard",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Color in RGB hex format",
            regex="^#[0-9a-fA-F]{6}$",
            example="#FF0000",
        ),
    ] = None

    short_name: Annotated[
        str | None,
        Field(
            title="Short name for particular enums",
            example="anim",
        ),
    ] = None

    disabled: Annotated[
        bool,
        Field(
            title="Is disabled",
            description="Enum item is visible, but not selectable",
            example=False,
        ),
    ] = False

    disabled_message: Annotated[
        str | None,
        Field(
            title="Disabled message",
            description="Message to show when the option is disabled",
            example="This option is not available",
        ),
    ] = None

    hidden: Annotated[
        bool,
        Field(
            title="Is hidden",
            description="Enum item is not visible in the dropdown",
            example=False,
        ),
    ] = False

    badges: Annotated[
        list[str] | None,
        Field(
            title="Badges",
            description="Extra badge labels to display next to the item",
            example=["beta"],
        ),
    ] = None

    @validator("label", pre=True, always=True)
    def set_label(cls, v: str | None, values: dict[str, Any]) -> str:
        if v is None and "value" in values:
            return str(values["value"])
        if v is None:
            return ""
        return v

    @validator("fulltext", pre=True, always=True)
    def set_fulltext(cls, v: list[str] | None, values: dict[str, Any]) -> list[str]:
        if v is not None:
            return v

        terms: set[str] = set()
        if "value" in values:
            terms |= slugify(str(values["value"]), make_set=True)
        if "label" in values and values["label"]:
            terms |= slugify(values["label"], make_set=True)
        if "description" in values and values["description"]:
            terms |= slugify(values["description"], make_set=True)
        return list(terms)
