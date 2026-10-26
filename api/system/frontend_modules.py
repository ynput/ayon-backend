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
    """Return the dev bundle the user is working on.

    Same choice the frontend makes in developer mode: the bundle active for the user,
    otherwise the newest dev bundle.
    """
    rows = await Postgres.fetch(
        """
        SELECT name, active_user FROM bundles
        WHERE is_dev AND is_archived IS FALSE
        ORDER BY created_at DESC
        """
    )
    for row in rows:
        if row["active_user"] == user_name:
            return row["name"]
    return rows[0]["name"] if rows else None


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
