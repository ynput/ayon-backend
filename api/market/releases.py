from datetime import datetime
from typing import Literal

from fastapi import Query

from ayon_server.installer.models import DependencyPackageManifest, InstallerManifest
from ayon_server.models import RestField, RestModel

from .common import get_market_data
from .router import router

DocsType = Literal["user", "admin", "developer"]


class ReleaseAddon(RestModel):
    name: str = RestField(..., min_length=1, max_length=64, title="Addon Name")
    title: str | None = RestField(
        None, min_length=1, max_length=64, title="Addon Title"
    )
    description: str | None = RestField(None, title="Addon Description")

    icon: str | None = RestField(None)
    preview: str | None = RestField(None)

    features: list[str] = RestField(default_factory=list)
    families: list[str] = RestField(default_factory=list)

    tags: list[str] = RestField(default_factory=list)
    docs: dict[DocsType, str] = RestField(default_factory=dict)
    github: str | None = RestField(None, title="GitHub Repository URL")
    discussion: str | None = RestField(None, title="Discussion URL")

    is_free: bool = RestField(True, title="Is this addon free?")

    version: str | None = RestField(None, title="Version")
    url: str | None = RestField(None, title="Download URL")
    checksum: str | None = RestField(
        None,
        description="Checksum of the zip file",
        example="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )
    mandatory: bool | None = RestField(None)


class ReleaseInfoModel(RestModel):
    name: str = RestField(..., title="Release name", example="2023.08-2D")
    label: str = RestField(..., title="Release label", example="2D Animation")
    created_at: datetime = RestField(default_factory=datetime.now)
    addons: list[ReleaseAddon] = RestField(default_factory=list)
    installers: list[InstallerManifest] | None = RestField(None)
    dependency_packages: list[DependencyPackageManifest] | None = RestField(None)


class ReleaseListItemModel(RestModel):
    name: str = RestField(..., title="Release name", example="2023.08-Kitsu")
    release: str = RestField(..., title="Release", example="2023.08")
    label: str = RestField(..., title="Release label", example="2D Animation")
    bio: str = RestField("", title="Release bio", example="2D Animation")
    icon: str = RestField("", title="Release icon", example="skeleton")
    created_at: datetime = RestField(...)
    is_latest: bool = RestField(...)
    addons: list[str] = RestField(...)
    mandatory_addons: list[str] = RestField(default_factory=list)


class ReleaseListModel(RestModel):
    releases: list[ReleaseListItemModel] = RestField(...)
    detail: str = ""


@router.get("/releases", response_model_exclude_none=True)
async def get_releases(list_all: bool = Query(False, alias="all")) -> ReleaseListModel:
    """Get the releases"""

    endpoint = "releases"
    if list_all:
        endpoint += "?all=true"
    result = await get_market_data(endpoint)
    return ReleaseListModel(releases=result["releases"])


@router.get("/releases/{release_name}", response_model_exclude_none=True)
async def get_release_info(release_name: str) -> ReleaseInfoModel:
    """Get the release info"""

    result = await get_market_data(f"releases/{release_name}")
    return ReleaseInfoModel(**result)
