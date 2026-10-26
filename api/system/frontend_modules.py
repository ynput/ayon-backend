from fastapi import Query

from ayon_server.addons.library import AddonLibrary
from ayon_server.addons.models import FrontendModules
from ayon_server.api.dependencies import AllowGuests, CurrentUser
from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel

from .router import router


class FrontendModuleListItem(OPModel):
    addon_name: str
    addon_version: str
    modules: FrontendModules


async def get_developer_bundle_name(user_name: str) -> str | None:
    """Return the user's active dev bundle, or None if they have none."""
    row = await Postgres.fetchrow(
        """
        SELECT name FROM bundles
        WHERE is_dev AND is_archived IS FALSE AND active_user = $1
        """,
        user_name,
    )
    return row["name"] if row else None


@router.get("/frontendModules", dependencies=[AllowGuests])
async def list_frontend_modules(
    user: CurrentUser,
    variant: str = Query(
        "production",
        description="production, staging, or developer (the user's dev bundle)",
    ),
) -> list[FrontendModuleListItem]:
    addon_library = AddonLibrary.getinstance()

    result = []

    if variant == "developer":
        # no dev bundle means there is nothing dev specific to load, use production
        variant = await get_developer_bundle_name(user.name) or "production"

    bundle_addons = await addon_library.get_addons_by_variant(variant)
    for addon in bundle_addons.values():
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
