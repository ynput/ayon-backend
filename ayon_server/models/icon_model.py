from typing import Annotated, Literal

from pydantic import BaseModel, Field

IconType = Literal["material-symbols", "url"]


class IconModel(BaseModel):
    type: Annotated[
        IconType,
        Field(
            title="Icon Type",
            example="material-symbols",
        ),
    ] = "url"

    name: Annotated[
        str | None,
        Field(
            title="Icon Name",
            description="The name of the icon (for type material-symbols)",
            example="icon_of_sin",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Icon Color",
            description="The color of the icon (for type material-symbols)",
            example="#FF0000",
        ),
    ] = None

    url: Annotated[
        str | None,
        Field(
            description="The URL of the icon (for type url)",
            example="https://example.com/icon.png",
        ),
    ] = None
