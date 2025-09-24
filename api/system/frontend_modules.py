from ayon_server.addons.library import AddonLibrary
from ayon_server.addons.models import FrontendModules
from ayon_server.api.dependencies import AllowGuests, CurrentUser
from ayon_server.types import OPModel

from .router import router


class FrontendModuleListItem(OPModel):
    addon_name: str
    addon_version: str
    modules: FrontendModules


@router.get("/frontendModules", dependencies=[AllowGuests])
async def list_frontend_modules(user: CurrentUser) -> list[FrontendModuleListItem]:
    addon_library = AddonLibrary.getinstance()

    result = []

    production_addons = await addon_library.get_addons_by_variant("production")
    for addon in production_addons.values():
        if not addon:
            continue

        frontend_modules = await addon.get_frontend_modules()

        if not frontend_modules:
            continue

        result.append(
            FrontendModuleListItem(
                addon_name=addon.name,
                addon_version=addon.version,
                modules=frontend_modules,
            )
        )

    return result
