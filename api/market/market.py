import semver

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import ForbiddenException

from .common import (
    get_local_latest_addon_versions,
    get_local_production_addon_versions,
    get_market_data,
    is_compatible,
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

        if (
            semver.compare(
                addon["latestVersion"],
                addon["currentProductionVersion"] or "0.0.0",
            )
            > 0
        ):
            addon["isOutdated"] = True

    return result


@router.get("/addons/{addon_name}")
async def market_addon_detail(user: CurrentUser, addon_name: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can access the market")

    result = await get_market_data("addons", addon_name)
    installed_addons = await get_local_latest_addon_versions()
    production_addons = await get_local_production_addon_versions()

    latest_compatible_version = None
    is_outdated = False

    for version in result.get("versions", []):
        required_version = version.get("ayonVersion")
        if required_version and not is_compatible(required_version):
            version["isCompatible"] = False

        else:
            version["isCompatible"] = True
            if (
                semver.compare(
                    version["version"], installed_addons.get(addon_name, "0.0.0")
                )
                > 0
            ):
                is_outdated = True

            if latest_compatible_version is None:
                latest_compatible_version = version["version"]
            elif semver.compare(version["version"], latest_compatible_version) > 0:
                latest_compatible_version = version["version"]

        version["isInstalled"] = (
            addon_name in installed_addons
            and installed_addons[addon_name] == version["version"]
        )
        version["isProduction"] = (
            addon_name in production_addons
            and production_addons[addon_name] == version["version"]
        )

    warning = None
    if result["latestVersion"] != latest_compatible_version:
        warning = "There are newer versions available, but they are not compatible with your Ayon version"

    result["latestVersion"] = latest_compatible_version
    result["warning"] = warning
    result["isOutdated"] = is_outdated

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

    required_version = result.get("ayonVersion")
    if required_version and not is_compatible(required_version):
        result["isCompatible"] = False
        result["url"] = None
    else:
        result["isCompatible"] = True

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
