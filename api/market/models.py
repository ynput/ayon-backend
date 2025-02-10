from datetime import datetime
from typing import Annotated, Literal

from ayon_server.types import Field, OPModel


class RestModel(OPModel):
    pass


### Copied from InstanceManager


class LinkModel(RestModel):
    type: Annotated[
        Literal["homepage", "github", "documentation", "license"],
        Field(
            title="Link type",
            example="github",
        ),
    ] = "homepage"
    label: Annotated[
        str | None,
        Field(
            title="Link label",
            example="ynput/my-addon",
        ),
    ] = None
    url: Annotated[
        str,
        Field(
            title="Link URL",
            example="https://github.com/ynput/my-addon",
        ),
    ]


class AddonListItem(RestModel):
    name: Annotated[str, Field(title="Addon name", example="maya")]
    title: Annotated[str, Field(title="Addon title", example="Maya")]
    description: Annotated[
        str | None,
        Field(
            description="Addon description",
            example="Maya is a 3D computer graphics application",
        ),
    ] = None
    org_name: Annotated[
        str | None,
        Field(
            title="Organization name",
            example="ynput-official",
        ),
    ] = None
    org_title: Annotated[
        str | None,
        Field(
            title="Organization title",
            example="Ynput",
        ),
    ] = None
    icon: Annotated[
        str | None,
        Field(
            title="Icon URL",
            example="https://example.com/maya.png",
        ),
    ] = None
    latest_version: Annotated[
        str | None,
        Field(
            description="Latest version of the addon",
            example="1.0.0",
        ),
    ] = None
    links: Annotated[
        list[LinkModel] | None,
        Field(
            description="Links to the addon's homepage and GitHub repository",
            example=[
                {"type": "github", "url": "https://github.com/ynput/ayon-maya"},
            ],
        ),
    ] = None
    available: Annotated[
        bool,
        Field(description="Addon is avaliable for download"),
    ] = True

    # ayon only
    current_production_version: Annotated[
        str | None, Field(title="Current production version", example="1.0.0")
    ] = None
    current_latest_version: Annotated[
        str | None, Field(title="Latest installed version", example="1.0.0")
    ] = None
    is_outdated: Annotated[
        bool, Field(title="Is the current version outdated", example=False)
    ] = False


class AddonList(RestModel):
    addons: Annotated[list[AddonListItem], Field(default_factory=list)]


class AddonVersionListItem(RestModel):
    version: Annotated[
        str,
        Field(
            title="Addon version",
            example="1.0.0",
        ),
    ]
    ayon_version: Annotated[
        str | None,
        Field(
            title="Ayon version",
            description="Required Ayon server version to run the addon",
            example="1.2.0",
        ),
    ] = None
    created_at: datetime | None = Field(None, example="2024-01-01T00:00:00Z")
    updated_at: datetime | None = Field(None, example="2024-01-01T00:00:00Z")

    # ayon only
    is_compatible: bool | None = Field(None, description="Is this version compatible?")
    is_installed: bool | None = Field(None, description="Is this version installed?")
    is_production: bool | None = Field(
        None, description="Is this version in production?"
    )


class AddonDetail(AddonListItem):
    versions: list[AddonVersionListItem] = Field(
        default_factory=list, description="A list of versions of this addon"
    )

    # ayon only
    warning: str | None = Field(
        None, description="A warning message to display to the user"
    )


class AddonVersionDetail(AddonListItem):
    version: str = Field(..., example="1.0.0")
    url: str | None = Field(None, example="https://example.com/maya-1.0.0.zip")
    alt_url: str | None = Field(None, example="https://example2.com/maya-1.0.0.zip")
    checksum: str | None = Field(None, example="a1b2c3d4e5f6g7h8i9j0")
    ayon_version: str | None = Field(
        None,
        description="The version of Ayon this version is compatible with",
        example="1.2.0",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When this version was created",
        example="2024-01-01T00:00:00Z",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="When this version was last updated",
        example="2024-01-01T00:00:00Z",
    )

    # ayon only
    is_installed: bool = Field(False, description="Is this version installed?")
    is_production: bool = Field(False, description="Is this version in production?")
    is_compatible: bool = Field(False, description="Is this version compatible?")
