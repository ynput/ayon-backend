import asyncio
import time
import traceback

from fastapi import Depends, Query

from ayon_server.addons import AddonLibrary
from ayon_server.addons.settings_caching import AddonSettingsCache, load_all_settings
from ayon_server.api.dependencies import CurrentUser, SiteID
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.redis import Redis
from ayon_server.logging import log_traceback, logger
from ayon_server.settings import BaseSettingsModel
from ayon_server.types import NAME_REGEX, PROJECT_NAME_REGEX
from ayon_server.utils import hash_data
from ayon_server.utils.request_coalescer import RequestCoalescer

from .models import AddonSettingsItemModel, AllSettingsResponseModel
from .router import router
from .settings_addons_list import get_addon_list_for_settings

_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


async def get_semaphore(limit: int = 30) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(limit)
    return _semaphores[loop]


async def _get_all_settings(
    user_name: str,
    site_id: str | None,
    bundle_name: str | None,
    project_name: str | None,
    project_bundle_name: str | None,
    variant: str,
    summary: bool,
    semaphore: asyncio.Semaphore,
) -> AllSettingsResponseModel:
    start_time = time.monotonic()
    cache_key = hash_data(
        (
            bundle_name,
            project_name,
            project_bundle_name,
            variant,
            user_name,
            site_id,
            summary,
        )
    )

    cached = await Redis.get_json("all-settings", cache_key)
    if cached:
        try:
            return AllSettingsResponseModel(**cached)
        except Exception:
            logger.trace("Invalid cached settings data, reloading from DB")
            pass

    addon_list = await get_addon_list_for_settings(
        bundle_name=bundle_name,
        project_name=project_name,
        project_bundle_name=project_bundle_name,
        variant=variant,
    )

    all_settings = await load_all_settings(
        addons=addon_list["addons"],
        variant=variant,
        project_name=project_name,
        user_name=user_name,
        site_id=site_id,
    )

    elapsed_time = time.monotonic() - start_time
    logger.trace(f"Settings preloaded in {elapsed_time:.02f} seconds")

    #
    # Iterate over all addons and load the settings
    #

    async with semaphore:
        start_time = time.monotonic()
        addon_result = []
        for addon_name, addon_version in addon_list["addons"].items():
            if addon_version is None:
                continue

            try:
                addon = AddonLibrary.addon(addon_name, addon_version)
            except NotFoundException:
                bundle_title = bundle_name or f"{variant} bundle"
                logger.warning(
                    f"Addon {addon_name} {addon_version} "
                    f"declared in {bundle_title} not found"
                )

                broken_reason = AddonLibrary.is_broken(addon_name, addon_version)

                addon_result.append(
                    AddonSettingsItemModel(
                        name=addon_name,
                        title=addon_name,
                        version=addon_version,
                        settings={},
                        site_settings=None,
                        is_broken=bool(broken_reason),
                        reason=broken_reason,
                    )
                )
                continue

            if project_bundle_name and addon_name not in addon_list["inherited_addons"]:
                overridable = addon.get_project_can_override_addon_version()
                if not overridable:
                    logger.error(
                        f"Addon {addon_name} {addon_version} "
                        f"declared in project bundle {project_bundle_name} "
                        f"cannot be overridden per project"
                    )
                    continue

            # Determine which scopes addon has settings for

            model = addon.get_settings_model()
            has_settings = False
            has_project_settings = False
            has_project_site_settings = False
            has_site_settings = bool(addon.site_settings_model)
            if model:
                has_project_settings = False
                for field in model.__fields__.values():
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
                key = addon.name, addon_version
                settings_cache = all_settings.get(key, AddonSettingsCache())

                if site_id:
                    site_settings = await addon.get_site_settings(
                        user_name,
                        site_id,
                        settings_cache=settings_cache,
                    )

                    if project_name is None:
                        # Studio level settings (studio level does not have)
                        # site overrides per se but it can have site settings
                        settings = await addon.get_studio_settings(
                            variant,
                            settings_cache=settings_cache,
                        )
                    else:
                        # Project and site is requested, so we are returning
                        # project level settings WITH site overrides
                        settings = await addon.get_project_site_settings(
                            project_name,
                            user_name,
                            site_id,
                            variant,
                            settings_cache=settings_cache,
                        )
                elif project_name:
                    # Project level settings (no site overrides)
                    settings = await addon.get_project_settings(
                        project_name,
                        variant,
                        settings_cache=settings_cache,
                    )
                else:
                    # Just studio level settings (no project, no site)
                    settings = await addon.get_studio_settings(
                        variant,
                        settings_cache=settings_cache,
                    )

            except Exception:
                log_traceback(f"Unable to load {addon_name} {addon_version} settings")
                addon_result.append(
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
                addon.settings_cache = None
                continue

            # Add addon to the result

            addon_result.append(
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
                    has_project_site_overrides=settings._has_site_overrides
                    if settings
                    else None,
                    settings=settings.dict() if (settings and not summary) else {},
                    site_settings=site_settings,
                )
            )

        # sort the result, save to cache and return

        addon_result.sort(key=lambda x: x.title.lower())

        elapsed_time = time.monotonic() - start_time
        logger.trace(f"Settings object generated in {elapsed_time:.02f} seconds")

        result = AllSettingsResponseModel(
            bundle_name=addon_list["bundle_name"],
            addons=addon_result,
            inherited_addons=list(addon_list.get("inherited_addons", set())),
        )

        # Cache the result
        await Redis.set(
            "all-settings",
            cache_key,
            result.json(),
            ttl=60 * 60,  # Cache for 1 hour
        )

        return result


@router.get("/settings", response_model_exclude_none=True)
async def get_all_settings(
    user: CurrentUser,
    site_id: SiteID,
    bundle_name: str | None = Query(
        None,
        title="Bundle name",
        description=(
            "Use explicit bundle name to get the addon list. "
            "Current production (or staging) will be used if not set"
        ),
        regex=NAME_REGEX,
    ),
    project_name: str | None = Query(
        None,
        title="Project name",
        description=(
            "Return project settings for the given project name. "
            "Studio settings will be returned if not set"
        ),
        regex=PROJECT_NAME_REGEX,
    ),
    project_bundle_name: str | None = Query(
        None,
        title="Project bundle name",
        description=(
            "Use explicit project bundle instead of the default one "
            "to resolve the project addons."
        ),
    ),
    variant: str = Query(
        "production",
        title="Variant",
        description=(
            "Variant of the settings to return. "
            "This field is also used to determine which bundle to use"
            "if bundle_name or project_bundle_name is not set"
        ),
    ),
    summary: bool = Query(
        False,
        title="Summary",
        description=(
            "Summary mode. When selected, do not return actual settings "
            "instead only return the basic information about the addons "
            "in the specified bundles"
        ),
    ),
    semaphore: asyncio.Semaphore = Depends(get_semaphore),
) -> AllSettingsResponseModel:
    """Return all addon settings

    ## Studio settings

    When project name is not specified, studio settings are returned

    ## Project settings

    When project_name is specified, endpoint returns project settings
    and if the project has a bundle override, it will return settings
    of the addons specified in the override.

    It is also possible to specify project_bundle_name to set the project
    bundle explicitly (for renderfarms)

    """

    coalesce = RequestCoalescer()
    return await coalesce(
        _get_all_settings,
        user_name=user.name,
        site_id=site_id,
        bundle_name=bundle_name,
        project_name=project_name,
        project_bundle_name=project_bundle_name,
        variant=variant,
        summary=summary,
        semaphore=semaphore,
    )
