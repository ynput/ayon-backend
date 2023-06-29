from typing import Any, Literal

from fastapi import Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import NAME_REGEX, Field, OPModel

from .router import router


class AddonSettingsItemModel(OPModel):
    name: str = Field(..., regex=NAME_REGEX)
    version: str = Field(..., regex=NAME_REGEX)

    # Final settings for the addon depending on the request (project, site)
    # it returns either studio, project or project/site settings
    settings: dict[str, Any] = Field(default_factory=dict)

    # If site_id is specified and the addon has site settings model,
    # return studio level site settings here
    site_settings: dict[str, Any] | None = Field(default_factory=dict)


class AllSettingsResponseModel(OPModel):
    bundle_name: str = Field(..., regex=NAME_REGEX)
    addons: list[AddonSettingsItemModel] = Field(default_factory=list)


@router.get("/settings", response_model_exclude_none=True)
async def get_all_settings(
    user: CurrentUser,
    bundle_name: str
    | None = Query(
        None,
        title="Bundle name",
        description="Production if not set",
        regex=NAME_REGEX,
    ),
    project_name: str
    | None = Query(
        None,
        title="Project name",
        description="Studio settings if not set",
        regex=NAME_REGEX,
    ),
    site_id: str
    | None = Query(
        None,
        title="Site ID",
    ),
    variant: Literal["production", "staging"] = Query("production"),
) -> AllSettingsResponseModel:
    pass

    if bundle_name is None:
        query = [
            """
            SELECT name, is_production, is_staging, data->'addons' as addons
            FROM bundles WHERE is_production IS TRUE
            """
        ]
    else:
        query = [
            """
            SELECT name, is_production, is_staging, data->'addons' as addons
            FROM bundles WHERE name = $1
            """,
            bundle_name,
        ]

    brow = await Postgres.fetch(*query)
    if not brow:
        raise NotFoundException(status_code=404, detail="Bundle not found")

    bundle_name = brow[0]["name"]
    addons = brow[0]["addons"]

    addon_result = []
    for addon_name, addon_version in addons.items():
        if addon_version is None:
            continue

        addon = AddonLibrary.addon(addon_name, addon_version)

        site_settings = None
        settings: BaseSettingsModel | None = None
        if site_id:
            site_settings = await addon.get_site_settings(user.name, site_id)

            if project_name is not None:
                settings = await addon.get_project_site_settings(
                    project_name,
                    user.name,
                    site_id,
                    variant,
                )
        elif project_name:
            settings = await addon.get_project_settings(project_name, variant)
        else:
            settings = await addon.get_studio_settings(variant)

        addon_result.append(
            AddonSettingsItemModel(
                name=addon_name,
                version=addon_version,
                settings=settings.dict() if settings else {},
                site_settings=site_settings,
            )
        )

    return AllSettingsResponseModel(
        bundle_name=bundle_name,
        addons=addon_result,
    )
