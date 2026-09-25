from datetime import datetime

from fastapi import Query

from ayon_server.installer.models import DependencyPackageManifest, InstallerManifest
from ayon_server.models import RestField, RestModel

from .common import get_market_data
from .models import AddonVersionDetail
from .router import router


class BaseReleaseInfo(RestModel):
    name: str = RestField(..., title="Release name", example="2023.08-Kitsu")
    label: str = RestField(..., title="Release label", example="2D Animation")
    release: str = RestField(..., title="Release", example="2023.08")
    description: str = RestField("", title="Release bio", example="2D Animation")
    icon: str = RestField("", title="Release icon", example="skeleton")
    created_at: datetime = RestField(...)
    mandatory_addons: list[str] = RestField(default_factory=list)


class ReleaseListItemModel(BaseReleaseInfo):
    is_latest: bool = RestField(...)
    addons: list[str] = RestField(...)


class ReleaseInfoModel(BaseReleaseInfo):
    addons: list[AddonVersionDetail] = RestField(default_factory=list)
    installers: list[InstallerManifest] | None = RestField(None)
    dependency_packages: list[DependencyPackageManifest] | None = RestField(None)


class ReleaseListModel(RestModel):
    releases: list[ReleaseListItemModel] = RestField(...)
    detail: str = ""


@router.get("/releases", response_model_exclude_none=True)
async def get_releases(list_all: bool = Query(False, alias="all")) -> ReleaseListModel:
    """Get the releases"""

    endpoint = "market/releases"
    if list_all:
        endpoint += "?all=true"
    result = await get_market_data(endpoint, api_version="v2")
    return ReleaseListModel(releases=result["releases"])


@router.get("/releases/{release_name}", response_model_exclude_none=True)
async def get_release_info(release_name: str) -> ReleaseInfoModel:
    """Get the release info"""

    result = await get_market_data(f"market/releases/{release_name}", api_version="v2")
    return ReleaseInfoModel(**result)
