import os

import aioshutil
from fastapi import Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import AyonException, ForbiddenException, NotFoundException

from .router import router


@router.delete("/{addon_name}", tags=["Addons"])
async def delete_addon(
    user: CurrentUser,
    addon_name: str,
    purge: bool = Query(False, title="Purge all data related to the addon"),
) -> EmptyResponse:
    """Delete an addon"""

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete addons")

    AddonLibrary.delete_addon_from_server(addon_name)


@router.delete("/{addon_name}/{addon_version}", tags=["Addons"])
async def delete_addon_version(
    user: CurrentUser,
    addon_name: str,
    addon_version: str,
    purge: bool = Query(False, title="Purge all data related to the addon"),
) -> EmptyResponse:
    """Delete an addon version"""

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete addons")

    AddonLibrary.delete_addon_from_server(addon_name, addon_version)

