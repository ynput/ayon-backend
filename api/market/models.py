from datetime import datetime
from typing import Literal

from ayon_server.types import Field, OPModel


class RestModel(OPModel):
    pass


### Copied from InstanceManager


class LinkModel(RestModel):
    type: Literal["homepage", "github"] = Field("homepage")
    url: str = Field(...)


class AddonListItem(RestModel):
    name: str
    title: str
    description: str | None = Field(None)
    org_name: str | None = Field(None)
    org_title: str | None = Field(None)
    icon: str | None = Field(None)
    latest_version: str | None = Field(None)
    links: list[LinkModel] | None = Field(None)

    # ayon only
    current_production_version: str | None = Field(None)
    current_latest_version: str | None = Field(None)
    is_outdated: bool | None = Field(None)


class AddonList(RestModel):
    addons: list[AddonListItem] = Field(default_factory=list)


class AddonVersionListItem(RestModel):
    version: str
    ayon_version: str | None = Field(None)
    created_at: datetime | None = Field(None)
    updated_at: datetime | None = Field(None)

    # ayon only
    is_compatible: bool | None = Field(None)
    is_installed: bool | None = Field(None)
    is_production: bool | None = Field(None)


class AddonDetail(AddonListItem):
    versions: list[AddonVersionListItem] = Field(default_factory=list)

    # ayon only
    warning: str | None = Field(
        None, description="A warning message to display to the user"
    )


class AddonVersionDetail(AddonListItem):
    version: str
    url: str | None = None
    alt_url: str | None = None
    checksum: str | None = None
    ayon_version: str | None = Field(
        None, description="The version of Ayon this version is compatible with"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When this version was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="When this version was last updated"
    )

    # ayon only
    is_installed: bool = Field(False, description="Is this version installed?")
    is_production: bool = Field(None, description="Is this version in production?")
