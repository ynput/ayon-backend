from typing import Any

from fastapi import APIRouter, Response
from nxtools import logging

from openpype.addons import AddonLibrary
from openpype.exceptions import NotFoundException
from openpype.lib.postgres import Postgres
from openpype.settings import extract_overrides, list_overrides
from openpype.types import Field, OPModel

#
# Router
#

router = APIRouter(prefix="/addons")


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


#
# [POST] /usd/resolve
#


class VersionInfo(OPModel):
    has_settings: bool = Field(default=False)
    frontend_scopes: list[str] = Field(default=[])


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


@router.get("", response_model=AddonList, tags=["Addon settings"])
async def list_addons():
    """List all available addons."""

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
            versions[version] = VersionInfo(
                has_settings=bool(addon.settings),
                frontend_scopes=addon.frontend_scopes,
            )

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


class AddonVersionConfig(OPModel):
    productionVersion: str | None = Field(None)
    stagingVersion: str | None = Field(None)


class AddonConfigRequest(OPModel):
    versions: dict[str, AddonVersionConfig] | None = Field(None)


@router.post("", tags=["Addon settings"])
async def configure_addons(payload: AddonConfigRequest):
    if payload.versions:
        for name, version_config in payload.versions.items():
            await Postgres.execute(
                """
                INSERT INTO addon_versions
                (name, production_version, staging_version) VALUES ($1, $2, $3)
                ON CONFLICT (name)
                DO UPDATE SET production_version = $2, staging_version = $3
                """,
                name,
                version_config.productionVersion,
                version_config.stagingVersion,
            )


#
# Addon settings + studio overrides
# TODO: Add ACL. Endpoints now does not check if the calls are authorized,
# because during the development it is useful to test it using curl.
#


@router.get("/{addon_name}/{version}/schema", tags=["Addon settings"])
async def get_addon_settings_schema(addon_name: str, version: str):
    """Return the JSON schema of the addon settings."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")

    if addon.settings is None:
        logging.error(f"No schema for addon {addon_name}")
        return {}

    schema = addon.settings.schema()
    schema["title"] = addon.friendly_name
    return schema


@router.get("/{addon_name}/{version}/settings", tags=["Addon settings"])
async def get_addon_studio_settings(addon_name: str, version: str):
    """Return the settings (including studio overrides) of the given addon."""

    if (addon := AddonLibrary.addon(addon_name, version)) is None:
        raise NotFoundException(f"Addon {addon_name} {version} not found")
    return await addon.get_studio_settings()


@router.post("/{addon_name}/{version}/settings", tags=["Addon settings"])
async def set_addon_studio_settings(
    payload: dict[str, Any],
    addon_name: str,
    version: str,
):
    """Set the studio overrides of the given addon."""

    addon = AddonLibrary.addon(addon_name, version)
    original = await addon.get_studio_settings()
    existing = await addon.get_studio_overrides()
    if (original is None) or (addon.settings is None):
        # This addon does not have settings
        return Response(status_code=400)
    data = extract_overrides(original, addon.settings(**payload), existing)

    # Do not use versioning during the development (causes headaches)
    await Postgres.execute(
        "DELETE FROM settings WHERE addon_name = $1 AND addon_version = $2",
        addon_name,
        version,
    )

    await Postgres.execute(
        """
        INSERT INTO settings (addon_name, addon_version, data)
        VALUES ($1, $2, $3)
        """,
        addon_name,
        version,
        data,
    )
    return Response(status_code=204)


@router.get("/{addon_name}/{version}/overrides", tags=["Addon settings"])
async def get_addon_studio_overrides(addon_name: str, version: str):
    addon = AddonLibrary.addon(addon_name, version)
    settings = await addon.get_studio_settings()
    overrides = await addon.get_studio_overrides()
    if settings is None:
        return {}
    return list_overrides(settings, overrides)


#
# Project overrides
#


@router.get("/{addon_name}/{version}/settings/{project_name}", tags=["Addon settings"])
async def get_addon_project_settings(addon_name: str, version: str, project_name: str):
    return {}


@router.get("/{addon_name}/{version}/overrides/{project_name}", tags=["Addon settings"])
async def get_addon_project_overrides(
    addon_name: str,
    version: str,
    project_name: str,
):
    return {}
