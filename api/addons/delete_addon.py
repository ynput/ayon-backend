import os

import aioshutil
from fastapi import Query

from ayon_server.addons import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.api.system import require_server_restart
from ayon_server.exceptions import AyonException, ForbiddenException, NotFoundException

# from ayon_server.lib.postgres import Postgres
from .router import router


async def delete_addon_directory(addon_name: str, addon_version: str | None = None):
    """Delete an addon or addon version"""
    library = AddonLibrary.getinstance()
    addon_definition = library.get(addon_name)
    if addon_definition is None:
        raise NotFoundException("Addon not found")

    addon_dir = addon_definition.addon_dir
    is_empty = not os.listdir(addon_dir)

    if not is_empty and addon_version is not None:
        addon = addon_definition.versions.get(addon_version)
        if addon is None:
            raise NotFoundException("Addon version not found")

        version_dir = addon.addon_dir
        try:
            await aioshutil.rmtree(version_dir)
        except Exception as e:
            raise AyonException(
                f"Failed to delete {addon_name} {addon_version} directory: {e}"
            )
        library.unload_addon(addon_name, addon_version, {"error": "Addon deleted"})

    is_empty = not os.listdir(addon_dir)

    if (addon_version is None) or is_empty:
        try:
            await aioshutil.rmtree(addon_dir)
        except Exception as e:
            raise AyonException(f"Failed to delete {addon_name} directory: {e}")
        library.data.pop(addon_name, None)
    await require_server_restart(None, "Restart the server to apply the addon changes.")


@router.delete("/{addon_name}")
async def delete_addon(
    user: CurrentUser,
    addon_name: str,
    purge: bool = Query(False, title="Purge all data related to the addon"),
) -> EmptyResponse:
    """Delete an addon"""

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete addons")

    await delete_addon_directory(addon_name)

    if purge:
        # TODO: implement purge
        pass

    return EmptyResponse()


@router.delete("/{addon_name}/{addon_version}")
async def delete_addon_version(
    user: CurrentUser,
    addon_name: str,
    addon_version: str,
    purge: bool = Query(False, title="Purge all data related to the addon"),
) -> EmptyResponse:
    """Delete an addon version"""

    if not user.is_admin:
        raise ForbiddenException("Only admins can delete addons")

    await delete_addon_directory(addon_name, addon_version)

    if purge:
        pass
        # TODO: implement purge

    return EmptyResponse()
