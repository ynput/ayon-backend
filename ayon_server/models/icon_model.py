from typing import Annotated, Literal

from .rest_model import RestField, RestModel

IconType = Literal["material-symbols", "url"]


class IconModel(RestModel):
    type: Annotated[
        IconType,
        RestField(
            title="Icon Type",
            example="material-symbols",
        ),
    ] = "url"

    name: Annotated[
        str | None,
        RestField(
            title="Icon Name",
            description="The name of the icon (for type material-symbols)",
            example="icon_of_sin",
        ),
    ] = None

    color: Annotated[
        str | None,
        RestField(
            title="Icon Color",
            description="The color of the icon (for type material-symbols)",
            example="#FF0000",
        ),
    ] = None

    url: Annotated[
        str | None,
        RestField(
            description="The URL of the icon (for type url)",
            example="https://example.com/icon.png",
        ),
    ] = None
