from typing import Any, Literal

from fastapi import Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import NAME_REGEX, Field, OPModel

from .router import router


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


@router.get("/settings/addons", deprecated=True)
async def get_all_addons_settings(
    user: CurrentUser,
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

    result: dict[str, dict[str, Any]] = {}
    versions: dict[str, str] = {}

    for addon_name, _addon in library.items():
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
                result[addon_name] = settings.dict()
                versions[addon_name] = addon_version
                continue

        settings = await active_addon.get_studio_settings(variant=variant)
        if settings is None:
            continue
        result[addon_name] = settings.dict()
        versions[addon_name] = addon_version

    return AddonSettingsResponse(settings=result, versions=versions)


@router.get("/settings/addons/siteSettings", deprecated=True)
async def get_all_site_settings(
    user: CurrentUser,
    variant: Literal["production", "staging"] = Query(
        "production",
        title="Settings variant",
    ),
    site: str | None = Query(None, regex=NAME_REGEX),
) -> AddonSettingsResponse:
    """Return site settings for all enabled addons.

    Those are 'global' site settings (from addon.site_settings_model)
    with no project overrides. When site is not specified, it will
    return the default settings provided by the model.
    """

    library = AddonLibrary.getinstance()

    active_versions = await library.get_active_versions()

    result: dict[str, dict[str, Any]] = {}
    versions: dict[str, str] = {}

    for addon_name, _addon in library.items():
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

        site_settings_model = active_addon.get_site_settings_model()
        if site_settings_model is None:
            continue

        data = {}
        query = """
            SELECT data FROM site_settings
            WHERE site_id = $1 AND addon_name = $2
            AND addon_version = $3 AND user_name = $4
        """
        async for row in Postgres.iterate(
            query, site, addon_name, addon_version, user.name
        ):
            data = row["data"]
            break

        result[addon_name] = site_settings_model(**data).dict()
        versions[addon_name] = addon_version

    return AddonSettingsResponse(settings=result, versions=versions)
