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

    That is done by resolving the absolute path and checking
    if it is a subpath of the root directory.
    """
    root_path = pathlib.Path(root_dir).resolve()
    requested_path = (root_path / path).resolve()
    if not requested_path.is_relative_to(root_path):
        raise NotFoundException("Invalid file path")

    if not str(requested_path).startswith(str(root_path) + os.sep):
        # This is an extra check to stop Copilot security checks from triggering
        # false positives about path traversal. both paths are already resolved.
        # and is_relative_to should be sufficient, but Copilot doen't understand that.
        #
        # >>> from pathlib import Path
        # >>> import os
        # >>> os.getcwd()
        # '/home/martas'
        # >>> root = "/home/martas"
        # >>> path = "../../etc/passwd"
        # >>> root_path = Path(root).resolve()
        # >>> requested_path = (root_path / path).resolve()
        # >>> requested_path
        # PosixPath('/etc/passwd')
        # >>> assert requested_path.is_relative_to(root_path)
        # Traceback (most recent call last):
        #   File "<stdin>", line 1, in <module>
        # AssertionError
        #
        raise NotFoundException("Invalid file path")

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
