__all__ = ["addon_static_router"]

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import NotFoundException

addon_static_router = APIRouter(prefix="/addons", include_in_schema=False)


@addon_static_router.get("/{addon_name}/{addon_version}/private/{path:path}")
async def get_private_addon_file(
    _: CurrentUser, addon_name: str, addon_version: str, path: str
):
    # AddonLibrary.addon will raise 404 if the addon is not found
    addon = AddonLibrary.addon(addon_name, addon_version)

    private_dir = addon.get_private_dir()
    if private_dir is None:
        raise NotFoundException("Addon does not have a private directory")

    file_path = os.path.join(private_dir, path)
    if not os.path.isfile(file_path):
        raise NotFoundException("File not found")

    return FileResponse(file_path)


@addon_static_router.get("/{addon_name}/{addon_version}/public/{path:path}")
async def get_public_addon_file(addon_name: str, addon_version: str, path: str):
    # AddonLibrary.addon will raise 404 if the addon is not found
    addon = AddonLibrary.addon(addon_name, addon_version)

    public_dir = addon.get_public_dir()
    if public_dir is None:
        raise NotFoundException("Addon does not have a public directory")

    file_path = os.path.join(public_dir, path)
    if not os.path.isfile(file_path):
        raise NotFoundException("File not found")

    return FileResponse(file_path)


@addon_static_router.get("/{addon_name}/{addon_version}/frontend/{path:path}")
async def get_frontend_addon_file(addon_name: str, addon_version: str, path: str):
    if path == "":
        path = "index.html"

    # AddonLibrary.addon will raise 404 if the addon is not NotFoundException
    addon = AddonLibrary.addon(addon_name, addon_version)

    frontend_dir = addon.get_frontend_dir()
    if frontend_dir is None:
        raise NotFoundException("Addon does not have a frontend directory")

    file_path = os.path.join(frontend_dir, path)
    if not os.path.isfile(file_path):
        raise NotFoundException("File not found")

    return FileResponse(file_path)
