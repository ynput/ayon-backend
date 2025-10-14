from typing import Annotated, Any

from pydantic import validator

from ayon_server.models import IconModel
from ayon_server.types import Field, OPModel, SimpleValue
from ayon_server.utils import slugify


class EnumItem(OPModel):
    """Attribute enum item."""

    value: Annotated[SimpleValue, Field(title="Enum value")]
    label: Annotated[str, Field(title="Enum label")]
    description: Annotated[str | None, Field(title="Enum item description")] = None
    fulltext: Annotated[list[str] | None, Field(title="Fulltext search terms")] = None
    group: Annotated[str | None, Field(title="Enum group")] = None

    icon: Annotated[
        str | IconModel | None,
        Field(
            title="Icon name",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Color in RGB hex format",
            regex="^#[0-9a-fA-F]{6}$",
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

        terms: set[str] = set(v or [])
        if "value" in values:
            terms |= slugify(str(values["value"]), make_set=True)
        if "label" in values and values["label"]:
            terms |= slugify(values["label"], make_set=True)
        if "description" in values and values["description"]:
            terms |= slugify(values["description"], make_set=True)
        return list(terms)
