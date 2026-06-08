# DEPRECATED: Remove

from typing import Literal

from fastapi import Response

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from ayon_server.helpers.migrate_addon_settings import migrate_addon_settings
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from .router import router

#
# Addons configuration
#


AddonEnvironment = Literal["production", "staging"]


async def copy_addon_variant(
    addon_name: str,
    copy_from: AddonEnvironment,
    copy_to: AddonEnvironment,
    with_project_overrides: bool = False,
):
    """Copy addon settings from one variant to another."""

    res = await Postgres.fetch(
        "SELECT * FROM addon_versions WHERE name = $1", addon_name
    )
    if not res:
        raise AyonException("Addon environment not found")

    source_version = res[0][f"{copy_from}_version"]
    target_version = res[0][f"{copy_to}_version"]

    if not source_version:
        raise AyonException("Source environment not set")
    if not target_version:
        raise AyonException("Target environment not set")

    try:
        source_addon = AddonLibrary.addon(addon_name, source_version)
        target_addon = AddonLibrary.addon(addon_name, target_version)
    except NotFoundException as exc:
        raise AyonException(str(exc)) from exc

    await migrate_addon_settings(
        source_addon,
        target_addon,
        source_variant=copy_from,
        target_variant=copy_to,
        with_projects=with_project_overrides,
    )


class VariantCopyRequest(OPModel):
    addon_name: str = Field(..., description="Addon name")
    copy_from: AddonEnvironment = Field(
        ...,
        description="Source variant",
        example="production",
    )
    copy_to: AddonEnvironment = Field(
        ...,
        description="Destination variant",
        example="staging",
    )
    with_project_overrides: bool = Field(
        False,
        description="Also copy project overrides for the addon",
        example=False,
    )


class AddonConfigRequest(OPModel):
    copy_variant: VariantCopyRequest | None = Field(None)


@router.post("", deprecated=True)
async def configure_addons(
    payload: AddonConfigRequest,
    user: CurrentUser,
):
    if not user.is_manager:
        raise ForbiddenException

    if payload.copy_variant is not None:
        await copy_addon_variant(
            addon_name=payload.copy_variant.addon_name,
            copy_from=payload.copy_variant.copy_from,
            copy_to=payload.copy_variant.copy_to,
            with_project_overrides=payload.copy_variant.with_project_overrides,
        )
        return Response(status_code=204)

    raise BadRequestException("Unsupported request")
