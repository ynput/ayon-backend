from datetime import datetime
from typing import Literal

import httpx
from fastapi import Request
from pydantic import Field

from ayon_server.api.dependencies import CurrentUser, YnputConnectKey
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.installer.models import DependencyPackageManifest, InstallerManifest
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router

DocsType = Literal["user", "admin", "developer"]


class ReleaseAddon(OPModel):
    name: str = Field(..., min_length=1, max_length=64, title="Addon Name")
    title: str | None = Field(None, min_length=1, max_length=64, title="Addon Title")
    description: str | None = Field(None, title="Addon Description")

    icon: str | None = Field(None)
    preview: str | None = Field(None)

    features: list[str] = Field(default_factory=list)
    families: list[str] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)
    docs: dict[DocsType, str] = Field(default_factory=dict)
    github: str | None = Field(None, title="GitHub Repository URL")
    discussion: str | None = Field(None, title="Discussion URL")

    is_free: bool = Field(True, title="Is this addon free?")

    version: str | None = Field(None, title="Version")
    url: str | None = Field(None, title="Download URL")
    checksum: str | None = Field(
        None,
        description="Checksum of the zip file",
        example="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )
    mandatory: bool | None = Field(None)


class ReleaseInfoModel(OPModel):
    name: str = Field(..., title="Release name", example="2023.08-2D")
    created_at: datetime = Field(default_factory=datetime.now)
    addons: list[ReleaseAddon] = Field(default_factory=list)
    installers: list[InstallerManifest] | None = Field(None)
    dependency_packages: list[DependencyPackageManifest] = Field(None)


class ReleaseListItemModel(OPModel):
    name: str = Field(..., title="Release name", example="2023.08-2D")
    bio: str = Field("", title="Release bio", example="2D Animation")
    icon: str = Field("", title="Release icon", example="skeleton")
    created_at: datetime = Field(...)
    is_latest: bool = Field(...)
    addons: list[str] = Field(...)


class ReleaseListModel(OPModel):
    releases: list[ReleaseListItemModel] = Field(...)


@router.post("/abort")
async def abort_onboarding(request: Request, user: CurrentUser) -> EmptyResponse:
    """Abort the onboarding process (disable nag screen)"""

    if not user.is_admin:
        raise ForbiddenException()

    await Postgres().execute(
        """
        INSERT INTO config (key, value)
        VALUES ('onboardingFinished', 'true'::jsonb)
        """
    )

    return EmptyResponse()


@router.post("/restart")
async def restart_onboarding(request: Request, user: CurrentUser) -> EmptyResponse:
    """Restart the onboarding process"""

    if not user.is_admin:
        raise ForbiddenException()

    await Postgres().execute(
        """
        DELETE FROM config WHERE key = 'onboardingFinished'
        """
    )

    return EmptyResponse()


@router.get("/releases", response_model_exclude_none=True)
async def get_releases(ynput_connect_key: YnputConnectKey) -> ReleaseListModel:
    """Get the releases"""

    params = {"key": ynput_connect_key}

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/releases",
            params=params,
        )

    return ReleaseListModel(**res.json())


@router.get("/releases/{release_name}", response_model_exclude_none=True)
async def get_release_info(
    ynput_connect_key: YnputConnectKey, release_name: str
) -> ReleaseInfoModel:
    """Get the release info"""

    params = {"key": ynput_connect_key}

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{ayonconfig.ynput_connect_url}/api/releases/{release_name}",
            params=params,
        )

    return ReleaseInfoModel(**res.json())
