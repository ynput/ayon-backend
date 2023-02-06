from typing import Any, Literal

from addons.router import route_meta, router
from fastapi import APIRouter, Depends, Query, Request, Response
from nxtools import logging

from addons import project_settings, site_settings, studio_settings
from ayon_server.addons import AddonLibrary
from ayon_server.addons.models import SourceInfo
from ayon_server.api.dependencies import dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    AyonException,
    BadRequestException,
    ForbiddenException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel

assert site_settings
assert studio_settings
assert project_settings


def register_addon_endpoints():
    """Register all addons endpoints in the router."""

    library = AddonLibrary.getinstance()
    for addon_name, addon_definition in library.items():
        for version in addon_definition.versions:

            addon = addon_definition.versions[version]
            addon_router = APIRouter(
                prefix=f"/{addon_name}/{version}",
                tags=[f"{addon_definition.friendly_name} {version}"],
            )

            # TODO: add a condition to check if the addon REST API is enabled
            # We should discuss where the information about the addon is stored
            # and how to enable/disable it. It doesn't make sense to have
            # it in the database, because when this function is called,
            # database is not yet initialized (and we want to avoid the async madness)
            # Maybe each Addon versionshould have an attribute to enable/disable it?

            for endpoint in addon.endpoints:
                path = endpoint["path"].lstrip("/")
                first_element = path.split("/")[0]
                if first_element in ["settings", "schema", "overrides"]:
                    logging.error(f"Unable to assing path to endpoint: {path}")
                    continue

                addon_router.add_api_route(
                    f"/{path}",
                    endpoint["handler"],
                    methods=[endpoint["method"]],
                    name=endpoint["name"],
                )
            router.include_router(addon_router)


register_addon_endpoints()


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


class AddonList(OPModel):
    addons: list[AddonListItem] = Field(..., description="List of available addons")


@router.get(
    "",
    response_model=AddonList,
    response_model_exclude_none=True,
    **route_meta,
)
async def list_addons(
    request: Request,
    details: bool = Query(False, title="Show details"),
):
    """List all available addons."""

    base_url = f"{request.url.scheme}://{request.url.netloc}"

    result = []
    library = AddonLibrary.getinstance()

    # maybe some ttl here?
    active_versions = await library.get_active_versions()

    # TODO: for each version, return the information
    # whether it has settings (and don't show the addon in the settings editor if not)

    for name, definition in library.data.items():
        vers = active_versions.get(definition.name, {})
        versions = {}
        for version, addon in definition.versions.items():
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

                elif not all([isinstance(x, SourceInfo) for x in source_info]):
                    logging.error(f"Invalid source info for {addon.name} {version}")
                    source_info = [x for x in source_info if isinstance(x, SourceInfo)]
                vinf["client_source_info"] = source_info

                vinf["services"] = addon.services or None
            versions[version] = VersionInfo(**vinf)

        result.append(
            AddonListItem(
                name=definition.name,
                title=definition.friendly_name,
                versions=versions,
                description=definition.__doc__ or "",
                production_version=vers.get("production"),
                staging_version=vers.get("staging"),
            )
        )
    result.sort(key=lambda x: x.name)
    return AddonList(addons=result)


#
# Addons configuration
#


AddonEnvironment = Literal["production", "staging"]


def semver_sort_key(item):
    parts = item.split(".")
    for i in range(len(parts)):
        if not parts[i].isdigit():
            parts[i:] = ["".join(parts[i:])]
            break
    parts = [int(part) if part.isdigit() else part for part in parts]
    return parts


async def copy_addon_variant(
    addon_name: str,
    copy_from: AddonEnvironment,
    copy_to: AddonEnvironment,
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
        key=lambda x: semver_sort_key(x["addon_version"]),
        reverse=True,
    )

    target_settings = {}

    for settings in source_settings:
        target_settings = settings["data"]
        if settings["addon_version"] == source_version:
            break

    # store the settings

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

    # update the active version

    await Postgres.execute(
        f"""
        UPDATE addon_versions
        SET {copy_to}_version = $1
        WHERE name = $2
        """,
        source_version,
        addon_name,
    )


class AddonVersionConfig(OPModel):
    production_version: str | None = Field(None)
    staging_version: str | None = Field(None)


class VariantCopyRequest(OPModel):
    addon_name: str = Field(..., description="Addon name")
    copy_from: AddonEnvironment = Field(
        ..., description="Source variant", example="production"
    )
    copy_to: AddonEnvironment = Field(
        ..., description="Destination variant", example="staging"
    )


class AddonConfigRequest(OPModel):
    copy_variant: VariantCopyRequest | None = Field(None)
    versions: dict[str, AddonVersionConfig] | None = Field(None)


@router.post("", **route_meta)
async def configure_addons(
    payload: AddonConfigRequest,
    user: UserEntity = Depends(dep_current_user),
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

    if payload.versions:
        for name, version_config in payload.versions.items():
            new_versions = version_config.dict(exclude_none=False, exclude_unset=True)
            if not new_versions:
                continue

            sets = []
            if "production_version" in new_versions:
                sets.append("production_version = $1")

            if "staging_version" in new_versions:
                sets.append("staging_version = $2")

            if not sets:
                continue

            query = f"""
                INSERT INTO addon_versions (name, production_version, staging_version)
                VALUES ($3, $1, $2)
                ON CONFLICT (name) DO UPDATE SET {", ".join(sets)}
            """

            await Postgres.execute(
                query,
                new_versions.get("production_version"),
                new_versions.get("staging_version"),
                name,
            )
        return Response(status_code=204)

    raise BadRequestException("Unsupported request")
