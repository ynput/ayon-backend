from datetime import datetime
from typing import Literal

from ayon_server.types import Field, OPModel


class RestModel(OPModel):
    pass


### Copied from InstanceManager


class LinkModel(RestModel):
    type: Literal["homepage", "github", "documentation"] = Field("homepage")
    label: str | None = Field(None)
    url: str = Field(...)


class AddonListItem(RestModel):
    name: str = Field(..., title="Addon name", example="maya")
    title: str = Field(..., title="Addon title", example="Maya")
    description: str | None = Field(
        None,
        description="Addon description",
        example="Maya is a 3D computer graphics application",
    )
    org_name: str | None = Field(
        None, description="Organization name", example="ynput-official"
    )
    org_title: str | None = Field(
        None, description="Organization title", example="Ynput"
    )
    icon: str | None = Field(None, example="maya.png")
    latest_version: str | None = Field(
        None, description="Latest version of the addon", example="1.0.0"
    )
    links: list[LinkModel] | None = Field(
        None,
        description="Links to the addon's homepage and GitHub repository",
        example=[
            {"type": "github", "url": "https://github.com/ynput/ayon-maya"},
        ],
    )

    # ayon only
    current_production_version: str | None = Field(None, example="1.0.0")
    current_latest_version: str | None = Field(None, example="1.0.0")
    is_outdated: bool = Field(False, example=False)


class AddonList(RestModel):
    addons: list[AddonListItem] = Field(default_factory=list)


class AddonVersionListItem(RestModel):
    version: str = Field(..., example="1.0.0")
    ayon_version: str | None = Field(None, example="1.2.0")
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
