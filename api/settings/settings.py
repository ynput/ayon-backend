import traceback
from typing import Any

from fastapi import Query
from nxtools import log_traceback, logging, slugify

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import NAME_REGEX, Field, OPModel

from .router import router


class AddonSettingsItemModel(OPModel):
    name: str = Field(..., title="Addon name", regex=NAME_REGEX, example="my-addon")
    title: str = Field(..., title="Addon title", example="My Addon")
    version: str = Field(..., title="Addon version", regex=NAME_REGEX, example="1.0.0")

    # None value means that project does not have overrides or project/site was not specified
    # in the request
    has_settings: bool = Field(False)
    has_project_settings: bool = Field(False)
    has_project_site_settings: bool = Field(False)
    has_site_settings: bool = Field(False)
    has_studio_overrides: bool | None = Field(None)
    has_project_overrides: bool | None = Field(None)
    has_project_site_overrides: bool | None = Field(None)

    # Final settings for the addon depending on the request (project, site)
    # it returns either studio, project or project/site settings
    settings: dict[str, Any] = Field(default_factory=dict)

    # If site_id is specified and the addon has site settings model,
    # return studio level site settings here
    site_settings: dict[str, Any] | None = Field(default_factory=dict)

    is_broken: bool = Field(False)
    reason: dict[str, str] | None = Field(None)


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
    variant: str = Query("production"),
    summary: bool = Query(False, title="Summary", description="Summary mode"),
) -> AllSettingsResponseModel | None:

    addons_settings = []
    library = AddonLibrary.get_instance()

    if bundle_name:
        addons = await library.get_bundle_addons(bundle_name)
    else:
        variants_bundle_names = await library.get_variants_bundle_name()
        bundle_name = variants_bundle_names.get(variant)
        addons = await library.get_bundle_addons(bundle_name)

    for addon in addons:
        addon_name_and_version, addon = addon

        if not addon:
            addon_name, addon_version = addon_name_and_version.split("-", 1)
            logging.warning(
                f"Addon {addon_name} {addon_version} "
                f"declared in {bundle_name} not initialized."
            )

            is_broken = library.broken_addons.get(addon_name_and_version, None)

            broken_reason = {"error": "Addon is not initialized"}

            if is_broken:
                broken_reason["traceback"] = str(is_broken)

            addons_settings.append(
                AddonSettingsItemModel(
                    name=addon_name,
                    title=addon_name,
                    version=addon_version,
                    settings={},
                    site_settings=None,
                    is_broken=bool(is_broken),
                    reason=broken_reason,
                )
            )
            continue

        addon_name = addon.name
        addon_version = addon.version
        # Determine which scopes addon has settings for
        model = addon.get_settings_model()
        has_settings = False
        has_project_settings = False
        has_project_site_settings = False
        has_site_settings = bool(addon.site_settings_model)

        if model:
            has_project_settings = False
            for field_name, field in model.__fields__.items():
                scope = field.field_info.extra.get("scope", ["studio", "project"])
                if "project" in scope:
                    has_project_settings = True
                if "site" in scope:
                    has_project_site_settings = True
                if "studio" in scope:
                    has_settings = True

        # Load settings for the addon
        site_settings = None
        settings: BaseSettingsModel | None = None

        try:
            if site_id:
                site_settings = await addon.get_site_settings(user.name, site_id)

                if project_name is None:
                    # Studio level settings (studio level does not have)
                    # site overrides per se but it can have site settings
                    settings = await addon.get_studio_settings(variant)
                else:
                    # Project and site is requested, so we are returning
                    # project level settings WITH site overrides
                    settings = await addon.get_project_site_settings(
                        project_name,
                        user.name,
                        site_id,
                        variant,
                    )
            elif project_name:
                # Project level settings (no site overrides)
                settings = await addon.get_project_settings(project_name, variant)
            else:
                # Just studio level settings (no project, no site)
                settings = await addon.get_studio_settings(variant)

        except Exception:
            log_traceback(f"Unable to load {addon_name} {addon_version} settings")
            addons_settings.append(
                AddonSettingsItemModel(
                    name=addon_name,
                    title=addon_name,
                    version=addon_version,
                    settings={},
                    site_settings=None,
                    is_broken=True,
                    reason={
                        "error": "Unable to load settings",
                        "traceback": traceback.format_exc(),
                    },
                )
            )
            continue

        # Add addon to the result

        addons_settings.append(
            AddonSettingsItemModel(
                name=addon_name,
                title=addon.title if addon.title else addon_name,
                version=addon_version,
                # Has settings means that addon has settings model
                has_settings=has_settings,
                has_project_settings=has_project_settings,
                has_project_site_settings=has_project_site_settings,
                has_site_settings=has_site_settings,
                # Has overrides means that addon has overrides for the requested
                # project/site
                has_studio_overrides=settings._has_studio_overrides
                if settings
                else None,
                has_project_overrides=settings._has_project_overrides
                if settings
                else None,
                has_site_overrides=settings._has_site_overrides if settings else None,
                settings=settings.dict() if (settings and not summary) else {},
                site_settings=site_settings,
            )
        )

    addons_settings.sort(key=lambda x: x.title.lower())

    return AllSettingsResponseModel(
        bundle_name=bundle_name,
        addons=addons_settings,
    )
