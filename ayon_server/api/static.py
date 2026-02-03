__all__ = ["addon_static_router"]

import os
import pathlib

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ayon_server.addons.library import AddonLibrary
from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import NotFoundException

addon_static_router = APIRouter(prefix="/addons", include_in_schema=False)


def serve_static_file(root_dir: str, path: str) -> FileResponse:
    """Serve a static file from the given root directory.

    Since the path is provided by the user, we need to ensure
    that it does not escape the given root directory.

    This is done by resolving the absolute path and checking
    that it is a subpath of the root directory.
    """
    # Resolve the root directory once to an absolute path.
    root_path = pathlib.Path(root_dir).resolve()

    # Construct the requested path relative to the root directory and
    # normalize it. Using resolve(strict=False) here normalizes ".."
    # segments without requiring the file to exist.
    requested_path = (root_path / pathlib.Path(path)).resolve(strict=False)

    # Ensure the requested path is inside the root directory. At this point
    # requested_path has been normalized, so checking that root_path is one
    # of its parents (or equal to it) guarantees that it cannot escape
    # root_path via ".." segments or absolute paths.
    if root_path != requested_path and root_path not in requested_path.parents:
        raise NotFoundException("Invalid file path")

    if not requested_path.is_file():
        raise NotFoundException("File not found")

    # Pass a plain string path to FileResponse after all validation checks.
    return FileResponse(str(requested_path))


@addon_static_router.get("/{addon_name}/{addon_version}/private/{path:path}")
def get_private_addon_file(
    _: CurrentUser, addon_name: str, addon_version: str, path: str
):
    # AddonLibrary.addon will raise 404 if the addon is not found
    addon = AddonLibrary.addon(addon_name, addon_version)

    private_dir = addon.get_private_dir()
    if private_dir is None:
        raise NotFoundException("Addon does not have a private directory")

    return serve_static_file(private_dir, path)


@addon_static_router.get("/{addon_name}/{addon_version}/public/{path:path}")
def get_public_addon_file(addon_name: str, addon_version: str, path: str):
    # AddonLibrary.addon will raise 404 if the addon is not found
    addon = AddonLibrary.addon(addon_name, addon_version)

    public_dir = addon.get_public_dir()
    if public_dir is None:
        raise NotFoundException("Addon does not have a public directory")
    return serve_static_file(public_dir, path)


@addon_static_router.get("/{addon_name}/{addon_version}/frontend/{path:path}")
def get_frontend_addon_file(addon_name: str, addon_version: str, path: str):
    if path == "":
        path = "index.html"

    # AddonLibrary.addon will raise 404 if the addon is not NotFoundException
    addon = AddonLibrary.addon(addon_name, addon_version)

    frontend_dir = addon.get_frontend_dir()
    if frontend_dir is None:
        raise NotFoundException("Addon does not have a frontend directory")
    return serve_static_file(frontend_dir, path)
