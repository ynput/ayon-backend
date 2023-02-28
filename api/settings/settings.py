from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from ayon_server.addons import AddonLibrary
from ayon_server.api import ResponseFactory, dep_current_user
from ayon_server.entities import UserEntity
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import NAME_REGEX, Field, OPModel

router = APIRouter(
    tags=["Addon settings"],
    responses={
        401: ResponseFactory.error(401),
        403: ResponseFactory.error(403),
    },
)


class AddonSettingsResponse(OPModel):
    settings: dict[str, dict[str, Any]] = Field(
        ...,
        title="Addon settings",
        description="Addon settings for each active addon",
        example={
            "my-addon": {
                "my-setting": "my-value",
                "my-other-setting": "my-other-value",
            },
        },
    )
    versions: dict[str, str] = Field(
        ...,
        title="Addon versions",
        description="Active versions of the addon for the given variant",
        example={"my-addon": "1.0.0"},
    )


@router.get("/settings/addons")
async def get_all_addons_settings(
    user: UserEntity = Depends(dep_current_user),
    variant: Literal["production", "staging"] = Query(
        "production",
        title="Settings variant",
    ),
    project: str | None = Query(None, regex=NAME_REGEX),
    site: str | None = Query(None, regex=NAME_REGEX),
) -> AddonSettingsResponse:
    """Return all addon settings for the project."""

    library = AddonLibrary.getinstance()

    active_versions = await library.get_active_versions()

    result: dict[str, BaseSettingsModel] = {}
    versions: dict[str, str] = {}

    for addon_name, addon in library.items():
        if addon_name not in active_versions:
            continue
        try:
            addon_version = active_versions[addon_name][variant]
        except KeyError:
            continue

        if not addon_version:
            continue

        try:
            active_addon = library.addon(addon_name, addon_version)
        except Exception:
            continue

        if project:
            if site:
                settings = await active_addon.get_project_site_settings(
                    project_name=project,
                    variant=variant,
                    user_name=user.name,
                    site_id=site,
                )
            else:
                settings = await active_addon.get_project_settings(
                    project_name=project,
                    variant=variant,
                )
            if settings:
                result[addon_name] = settings
                versions[addon_name] = addon_version
                continue

        settings = await active_addon.get_studio_settings(variant=variant)
        if settings is None:
            continue
        result[addon_name] = settings
        versions[addon_name] = addon_version

    return AddonSettingsResponse(settings=result, versions=versions)
