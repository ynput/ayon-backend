from .common import get_marketplace_data
from .router import router


@router.get("/addons")
async def market_addon_list():
    result = await get_marketplace_data("addons")
    return result


@router.get("/addons/{addon_name}")
async def market_addon_detail(addon_name: str):
    result = await get_marketplace_data("addons", addon_name)
    return result


@router.get("/addons/{addon_name}/{addon_version}")
async def market_addon_version_detail(addon_name: str, addon_version: str):
    result = await get_marketplace_data("addons", addon_name, addon_version)
    return result
