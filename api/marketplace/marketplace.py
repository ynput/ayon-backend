from .common import (
    get_local_latest_addon_versions,
    get_local_production_addon_versions,
    get_marketplace_data,
)
from .router import router


@router.get("/addons")
async def market_addon_list():
    result = await get_marketplace_data("addons")
    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()

    for addon in result.get("addons", []):
        addon["currentProductionVersion"] = production_addons.get(addon["name"])
        addon["currentLatestVersion"] = installed_addons.get(addon["name"])
    return result


@router.get("/addons/{addon_name}")
async def market_addon_detail(addon_name: str):
    result = await get_marketplace_data("addons", addon_name)
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
async def market_addon_version_detail(addon_name: str, addon_version: str):
    result = await get_marketplace_data("addons", addon_name, addon_version)

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
