# DEPRECATED: Remove

from typing import Literal

import semver
from fastapi import Response

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
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
    project_name: str | None = None,
):
    """Copy addon settings from one variant to another."""

    res = await Postgres.fetch(
        "SELECT * FROM addon_versions WHERE name = $1", addon_name
    )
    if not res:
        raise AyonException("Addon environment not found")

    source_version = res[0][f"{copy_from}_version"]

    if not source_version:
        raise AyonException("Source environment not set")

    # Get the settings

    source_settings = await Postgres.fetch(
        """
        SELECT addon_version, data FROM settings
        WHERE addon_name = $1 AND variant = $2
        """,
        addon_name,
        copy_from,
    )

    if source_version not in [x["addon_version"] for x in source_settings]:
        source_settings.append({"addon_version": source_version, "data": {}})

    source_settings.sort(
        key=lambda x: semver.VersionInfo.parse(x["addon_version"]),
        reverse=True,
    )

    target_settings = {}

    for settings in source_settings:
        target_settings = settings["data"]
        if settings["addon_version"] == source_version:
            break

    # store the settings

    # TODO: Emit change event

    await Postgres.execute(
        """
        INSERT INTO settings (addon_name, addon_version, variant, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (addon_name, addon_version, variant) DO UPDATE
        SET data = $4
        """,
        addon_name,
        source_version,
        copy_to,
        target_settings,
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
        )
        return Response(status_code=204)

    raise BadRequestException("Unsupported request")
