from datetime import datetime

import httpx
from fastapi import Request
from pydantic import Field

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException
from ayon_server.installer.models import DependencyPackageManifest, InstallerManifest
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router


class ReleaseAddon(OPModel):
    name: str = Field(..., example="tvpaint")
    version: str = Field(..., example="1.0.0")
    url: str = Field(
        ...,
        description="URL to download the addon zip file",
        example="https://get.ayon.io/addons/tvpaint-1.0.0.zip",
    )
    checksum: str | None = Field(
        None,
        description="Checksum of the zip file",
        example="sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )


class ReleaseInfoModel(OPModel):
    name: str = Field(..., title="Release name", example="2023.08-2D")
    created_at: datetime = Field(default_factory=datetime.now)
    addons: list[ReleaseAddon] = Field(default_factory=list)
    installers: list[InstallerManifest] | None = Field(None)
    dependency_packages: list[DependencyPackageManifest] = Field(None)


@router.post("/abort")
async def abort_onboarding(request: Request, user: CurrentUser) -> EmptyResponse:
    """Abort the onboarding process (disable nag screen)"""

    if user.is_admin:
        raise ForbiddenException()

    await Postgres().execute(
        """
        INSERT INTO config (key, value)
        VALUES ('onboardingFinished', 'true'::jsonb)
        """
    )

    return EmptyResponse()


@router.get("/release")
async def get_release_info() -> ReleaseInfoModel:
    """Get the release info"""

    async with httpx.AsyncClient() as client:
        res = await client.get(f"{ayonconfig.ynput_connect_url}/api/releases/latest")

    return ReleaseInfoModel(**res.json())
