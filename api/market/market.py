from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException

from .common import (
    get_local_latest_addon_versions,
    get_local_production_addon_versions,
    get_market_data,
)
from .router import router


@router.get("/addons")
async def market_addon_list(user: CurrentUser):

    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("addons")
    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()

    for addon in result.get("addons", []):
        addon["currentProductionVersion"] = production_addons.get(addon["name"])
        addon["currentLatestVersion"] = installed_addons.get(addon["name"])
    return result


@router.get("/addons/{addon_name}")
async def market_addon_detail(user: CurrentUser, addon_name: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("addons", addon_name)
    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()
    for version in result.get("versions", []):
        version["isInstalled"] = (
            addon_name in installed_addons
            and installed_addons[addon_name] == version["version"]
        )
        version["isProduction"] = (
            addon_name in production_addons
            and production_addons[addon_name] == version["version"]
        )
    return result


@router.get("/addons/{addon_name}/{addon_version}")
async def market_addon_version_detail(
    user: CurrentUser,
    addon_name: str,
    addon_version: str,
):

    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("addons", addon_name, addon_version)

    # is installed?

    installed_addons = await get_local_latest_addon_versions()
    result["isInstalled"] = (
        addon_name in installed_addons and installed_addons[addon_name] == addon_version
    )

    # is production?

    production_addons = await get_local_production_addon_versions()
    result["isProduction"] = (
        addon_name in production_addons
        and production_addons[addon_name] == addon_version
    )

    return result
