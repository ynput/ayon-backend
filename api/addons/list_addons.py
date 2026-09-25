from typing import Any, Literal

import semver
from fastapi import Query, Request

from ayon_server.addons import AddonLibrary
from ayon_server.addons.models import FrontendScopes, SourceInfo, SourceInfoTypes
from ayon_server.api.dependencies import AllowGuests, CurrentUser
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils.hashing import hash_data

from .router import router


class VersionInfo(OPModel):
    has_settings: bool = Field(default=False)
    has_site_settings: bool = Field(default=False)
    frontend_scopes: FrontendScopes = Field(default_factory=dict)
    client_pyproject: dict[str, Any] | None = Field(None)
    client_source_info: list[SourceInfo] | None = Field(None)
    services: dict[str, Any] | None = Field(None)
    is_broken: bool = Field(False)
    reason: dict[str, str] | None = Field(None)
    project_can_override_addon_version: bool = Field(False)


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
    system: bool = Field(False, description="Is the addon a system addon?")
    project_can_override_addon_version: bool = Field(
        False, description="Allow project override"
    )


class AddonList(OPModel):
    addons: list[AddonListItem] = Field(..., description="List of available addons")


async def _get_addon_list(base_url: str, details: bool) -> list[AddonListItem]:
    ns = "addon-list"
    key = hash_data((base_url, details))

    addon_list = await Redis.get_json(ns, key)
    if addon_list is not None:
        return [AddonListItem(**item) for item in addon_list]

    logger.trace("Fetching addon list")

    result = []
    library = AddonLibrary.getinstance()

    # maybe some ttl here?
    active_versions = await library.get_active_versions()

    for definition in library.data.values():
        addon = None
        vers = active_versions.get(definition.name, {})
        versions = {}
        items = list(definition.versions.items())
        items.sort(key=lambda x: semver.VersionInfo.parse(x[0]))
        for version, addon in items:
            pcoav = addon.get_project_can_override_addon_version()
            vinf = {
                "has_settings": bool(addon.get_settings_model()),
                "has_site_settings": bool(addon.get_site_settings_model()),
                "frontend_scopes": await addon.get_frontend_scopes(),
                "project_can_override_addon_version": pcoav,
            }
            if details:
                vinf["client_pyproject"] = await addon.get_client_pyproject()

                source_info = await addon.get_client_source_info(base_url=base_url)
                if source_info is None:
                    pass

                elif not all(isinstance(x, SourceInfoTypes) for x in source_info):
                    logger.error(
                        f"Invalid source info for {addon.name} {addon.version}"
                    )
                    source_info = [
                        x for x in source_info if isinstance(x, SourceInfoTypes)
                    ]
                vinf["client_source_info"] = source_info
                vinf["services"] = addon.services or None

            versions[version] = VersionInfo(**vinf)

        for version, reason in library.get_broken_versions(definition.name).items():
            versions[version] = VersionInfo(is_broken=True, reason=reason)

        if not versions:
            continue

        result.append(
            AddonListItem(
                name=definition.name,
                title=definition.friendly_name,
                versions=versions,
                description=definition.__doc__ or "",
                production_version=vers.get("production"),
                system=bool(addon.system) if addon is not None else False,
                staging_version=vers.get("staging"),
                addon_type=addon.addon_type if addon is not None else "server",
                project_can_override_addon_version=definition.project_can_override_addon_version,
            )
        )

    result.sort(key=lambda x: x.name)
    await Redis.delete_ns("addon-list")
    await Redis.set_json("addon-list", key, [addon.dict() for addon in result])
    return result


@router.get("", response_model_exclude_none=True, dependencies=[AllowGuests])
async def list_addons(
    request: Request,
    user: CurrentUser,
    details: bool = Query(False, title="Show details"),
) -> AddonList:
    """List all available addons."""

    base_url = f"{request.url.scheme}://{request.url.netloc}"
    addon_list = await _get_addon_list(base_url, details)
    if not user.is_admin:
        addon_list = [addon for addon in addon_list if not addon.system]
    return AddonList(addons=addon_list)
