from typing import Any

from addons.router import route_meta, router
from fastapi import APIRouter, Depends, Query, Request
from nxtools import logging

from addons import project_settings, studio_settings
from openpype.addons import AddonLibrary
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.exceptions import ForbiddenException
from openpype.lib.postgres import Postgres
from openpype.types import Field, OPModel

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


class ClientSourceInfo(OPModel):
    type: str
    path: str


class VersionInfo(OPModel):
    has_settings: bool = Field(default=False)
    frontend_scopes: dict[str, Any] = Field(default_factory=dict)
    client_pyproject: dict[str, Any] | None = Field(None)
    client_source_info: list[ClientSourceInfo] | None = Field(None)
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
                "frontend_scopes": addon.frontend_scopes,
            }
            if details:
                vinf["client_pyproject"] = await addon.get_client_pyproject()
                vinf["client_source_info"] = await addon.get_client_source_info(
                    base_url=base_url
                )
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


class AddonVersionConfig(OPModel):
    productionVersion: str | None = Field(None)
    stagingVersion: str | None = Field(None)


class AddonConfigRequest(OPModel):
    versions: dict[str, AddonVersionConfig] | None = Field(None)


@router.post("", **route_meta)
async def configure_addons(
    payload: AddonConfigRequest,
    user: UserEntity = Depends(dep_current_user),
):
    if not user.is_manager:
        raise ForbiddenException

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
