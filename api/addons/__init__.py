from typing import Any, Literal

from fastapi import Query, Request, Response
from nxtools import logging

import semver

from ayon_server.addons import AddonLibrary
from ayon_server.addons.models import SourceInfo
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

from . import delete_addon, install, project_settings, site_settings, studio_settings
from .router import route_meta, router

assert install
assert site_settings
assert studio_settings
assert project_settings
assert delete_addon


class VersionInfo(OPModel):
    has_settings: bool = Field(default=False)
    has_site_settings: bool = Field(default=False)
    frontend_scopes: dict[str, Any] = Field(default_factory=dict)
    client_pyproject: dict[str, Any] | None = Field(None)
    client_source_info: list[SourceInfo] | None = Field(None)
    services: dict[str, Any] | None = Field(None)


class AddonListItem(OPModel):
    name: str = Field(..., description="Machine friendly name of the addon")
    title: str = Field(..., description="Human friendly title of the addon")
    versions: dict[str, VersionInfo] = Field(
        ..., description="List of available versions"
    )
    description: str = Field(..., description="Addon description")
    production_version: str | None = Field(
        None,
        description="Production version of the addon",
    )
    staging_version: str | None = Field(
        None,
        description="Staging version of the addon",
    )
    addon_type: Literal["server", "pipeline"] = Field(
        ..., description="Type of the addon"
    )
    system: bool | None = Field(None, description="Is the addon a system addon?")


class AddonList(OPModel):
    addons: list[AddonListItem] = Field(..., description="List of available addons")


@router.get("", response_model_exclude_none=True, **route_meta)
async def list_addons(
    request: Request,
    user: CurrentUser,
    details: bool = Query(False, title="Show details"),
) -> AddonList:
    """List all available addons."""

    base_url = f"{request.url.scheme}://{request.url.netloc}"

    result = []
    library = AddonLibrary.getinstance()

    # maybe some ttl here?
    active_versions = await library.get_active_versions()

    for definition in library.data.values():
        vers = active_versions.get(definition.name, {})
        versions = {}
        is_system = False
        items = list(definition.versions.items())
        items.sort(key=lambda x: semver.VersionInfo.parse(x[0]))
        for version, addon in items:
            if addon.system:
                if not user.is_admin:
                    continue
                is_system = True

            vinf = {
                "has_settings": bool(addon.get_settings_model()),
                "has_site_settings": bool(addon.get_site_settings_model()),
                "frontend_scopes": addon.frontend_scopes,
            }
            if details:
                vinf["client_pyproject"] = await addon.get_client_pyproject()

                source_info = await addon.get_client_source_info(base_url=base_url)
                if source_info is None:
                    pass

                elif not all(isinstance(x, SourceInfo) for x in source_info):
                    logging.error(f"Invalid source info for {addon.name} {version}")
                    source_info = [x for x in source_info if isinstance(x, SourceInfo)]
                vinf["client_source_info"] = source_info

                vinf["services"] = addon.services or None
            versions[version] = VersionInfo(**vinf)

        if not versions:
            continue

        result.append(
            AddonListItem(
                name=definition.name,
                title=definition.friendly_name,
                versions=versions,
                description=definition.__doc__ or "",
                production_version=vers.get("production"),
                system=is_system or None,
                staging_version=vers.get("staging"),
                addon_type=addon.addon_type,
            )
        )
    result.sort(key=lambda x: x.name)
    return AddonList(addons=result)


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

    # TODO: deprecated. Remove
    # update the active version
    #
    # await Postgres.execute(
    #     f"""
    #     UPDATE addon_versions
    #     SET {copy_to}_version = $1
    #     WHERE name = $2
    #     """,
    #     source_version,
    #     addon_name,
    # )


class AddonVersionConfig(OPModel):
    production_version: str | None = Field(None)
    staging_version: str | None = Field(None)


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
    # versions: dict[str, AddonVersionConfig] | None = Field(None)


@router.post("", **route_meta)
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

    # TODO: Deprecated. Replaced with bundles
    # if payload.versions:
    #     for name, version_config in payload.versions.items():
    #         new_versions = version_config.dict(exclude_none=False, exclude_unset=True)
    #         if not new_versions:
    #             continue
    #
    #         sets = []
    #         if "production_version" in new_versions:
    #             sets.append("production_version = $1")
    #
    #         if "staging_version" in new_versions:
    #             sets.append("staging_version = $2")
    #
    #         if not sets:
    #             continue
    #
    #         query = f"""
    #             INSERT INTO addon_versions (name, production_version, staging_version)
    #             VALUES ($3, $1, $2)
    #             ON CONFLICT (name) DO UPDATE SET {", ".join(sets)}
    #         """
    #
    #         await Postgres.execute(
    #             query,
    #             new_versions.get("production_version"),
    #             new_versions.get("staging_version"),
    #             name,
    #         )
    #     return Response(status_code=204)

    raise BadRequestException("Unsupported request")
