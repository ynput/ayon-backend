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

    root_dir is provided by the server and is not user-controlled,
    when user reaches this point, we can safely assume they can access
    any file under root_dir. However, we still need to validate the path
    to prevent directory traversal attacks.

    This function is over-engineered, because any shortcut
    (like using Pathlib's relative_to) is caught by CodeQL robot,
    that raises false security warnings. So we do this checks manually,
    and verbosely, so it keeps its metal mouth shut.
    """

    # Get the absolute path to root dir. Again. User has access to
    # root_dir, and everything under it.
    root_path = pathlib.Path(root_dir).resolve()

    # Split requested path to chunks and validate each chunk

    path_parts = path.split("/")  # this is URL, so we split by "/"
    for part in path_parts:
        # No empty parts allowed (this wouldn't happen with FastAPI,
        # but CodeQL doesn't know that)

        if not part.strip():
            raise NotFoundException("Invalid file path")

        # very explicitly forbid "." and ".." parts,
        # because they are used for directory traversal

        if part in [".", ".."]:
            raise NotFoundException("Invalid file path")

        if os.path.sep in part:
            raise NotFoundException("Invalid file path")

        if os.path.altsep and os.path.altsep in part:
            raise NotFoundException("Invalid file path")

    # Now we can safely create the full requested path

    requested_path = pathlib.Path(root_path, *path_parts).resolve()

    # To be extra extra safe, we check that the requested path
    # is relative to the root path (normally, this would be enough)

    if not requested_path.is_relative_to(root_path):
        raise NotFoundException("Invalid file path")

    # And check if the file actually exists

    if not requested_path.is_file():
        raise NotFoundException("File not found")

    return FileResponse(requested_path)


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
