from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.types import OPModel

from .router import router


class FrontendModuleListItem(OPModel):
    addon_name: str
    addon_version: str
    modules: dict[str, list[str]]


@router.get("/frontendModules", tags=["System"])
async def list_frontend_modules(user: CurrentUser) -> list[FrontendModuleListItem]:
    addon_library = AddonLibrary.getinstance()

    result = []

    production_addons = await addon_library.get_addons_by_variant("production")
    for addon in production_addons.values():
        if not addon:
            continue

        if not addon.frontend_modules:
            continue

        result.append(
            FrontendModuleListItem(
                addon_name=addon.name,
                addon_version=addon.version,
                modules=addon.frontend_modules,
            )
        )

    return result
