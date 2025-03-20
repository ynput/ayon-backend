import semver
from fastapi import BackgroundTasks

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException
from ayon_server.metrics import post_metrics

from .common import (
    get_local_latest_addon_versions,
    get_local_production_addon_versions,
    get_market_data,
    is_compatible,
)
from .models import (
    AddonDetail,
    AddonList,
    AddonVersionDetail,
)
from .router import router


@router.get("/addons")
async def market_addon_list(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> AddonList:
    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("market/addons", api_version="v2")
    addon_list = AddonList(addons=result.get("addons", []))

    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()

    for addon in addon_list.addons:
        addon.current_production_version = production_addons.get(addon.name)
        addon.current_latest_version = installed_addons.get(addon.name)

        if (
            addon.latest_version
            and semver.compare(
                addon.latest_version,
                addon.current_latest_version or "0.0.0",
            )
            > 0
        ):
            addon.is_outdated = True
    background_tasks.add_task(post_metrics)
    return addon_list


@router.get("/addons/{addon_name}")
async def market_addon_detail(user: CurrentUser, addon_name: str) -> AddonDetail:
    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("market/addons", addon_name, api_version="v2")
    addon_detail = AddonDetail(**result)

    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()

    latest_compatible_version = None
    is_outdated = False

    addon_detail.current_production_version = production_addons.get(addon_name)
    addon_detail.current_latest_version = installed_addons.get(addon_name)

    for version in addon_detail.versions:
        required_version = version.ayon_version
        if required_version and not is_compatible(required_version):
            version.is_compatible = False

        else:
            version.is_compatible = True
            if (
                semver.compare(
                    version.version, installed_addons.get(addon_name, "0.0.0")
                )
                > 0
            ):
                is_outdated = True

            if latest_compatible_version is None:
                latest_compatible_version = version.version
            elif semver.compare(version.version, latest_compatible_version) > 0:
                latest_compatible_version = version.version

        version.is_installed = (
            addon_name in installed_addons
            and installed_addons[addon_name] == version.version
        )
        version.is_production = (
            addon_name in production_addons
            and production_addons[addon_name] == version.version
        )

    warning = None
    if addon_detail.latest_version != latest_compatible_version:
        warning = (
            "There are newer versions available, "
            "but they are not compatible with your Ayon version"
        )

    addon_detail.latest_version = latest_compatible_version
    addon_detail.warning = warning
    addon_detail.is_outdated = is_outdated

    return addon_detail


@router.get("/addons/{addon_name}/{addon_version}")
async def market_addon_version_detail(
    user: CurrentUser,
    addon_name: str,
    addon_version: str,
) -> AddonVersionDetail:
    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data(
        "market/addons", addon_name, addon_version, api_version="v2"
    )
    version_detail = AddonVersionDetail(**result)

    required_version = version_detail.ayon_version
    if required_version and not is_compatible(required_version):
        version_detail.is_compatible = False
        version_detail.url = None
    else:
        version_detail.is_compatible = True

    # is installed?

    installed_addons = await get_local_latest_addon_versions()
    version_detail.is_installed = (
        addon_name in installed_addons and installed_addons[addon_name] == addon_version
    )

    # is production?

    production_addons = await get_local_production_addon_versions()
    version_detail.is_production = (
        addon_name in production_addons
        and production_addons[addon_name] == addon_version
    )

    return version_detail
