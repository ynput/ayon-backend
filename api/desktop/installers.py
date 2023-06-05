import json
import os
import shutil
from typing import Literal

import aiofiles
from fastapi import Query, Request
from nxtools import logging
from starlette.responses import FileResponse

from ayon_server.api.dependencies import CurrentUser
from ayon_server.exceptions import AyonException, ForbiddenException
from ayon_server.types import Field, OPModel

from .router import router

#
# Models
#

Platform = Literal["windows", "linux", "darwin"]


class InstallerPostModel(OPModel):
    version: str
    platform: Platform
    filename: str = Field(..., description="Name of the package")
    python_version: str
    python_modules: dict[str, str] = Field(default_factory=dict)


class InstallerModel(InstallerPostModel):
    file_exists: bool = Field(False, description="Whether the file exists")
    file_size: int | None = Field(None, description="Size of the package in bytes")


#
# Helpers
#


def get_installer_root() -> str:
    root = "/storage/installers"
    if not os.path.isdir(root):
        try:
            os.makedirs(root)
        except Exception as e:
            raise AyonException(f"Failed to create installer directory: {e}")
    return root


def get_version_dir(version: str) -> str:
    """Get path to version directory."""
    root = f"{get_installer_root()}/{version}"
    if not os.path.isdir(root):
        try:
            os.makedirs(root)
        except Exception as e:
            raise AyonException(f"Failed to create installer directory: {e}")
    return root


def get_manifest_by_filename(version: str, filename: str) -> InstallerModel | None:
    version_dir = get_version_dir(version)

    # ensure the file is specified in one of the manifest files
    for platform in Platform.__args__:
        manifest_file = os.path.join(version_dir, f"{platform}.json")
        if not os.path.isfile(manifest_file):
            continue
        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load manifest file {manifest_file}: {e}")
            continue

        if manifest.get("filename") == filename:
            return InstallerModel(
                **manifest,
                file_exists=True,
                file_size=os.path.getsize(manifest_file),
            )


#
# API
#


@router.get("/installers")
async def list_installers(
    user: CurrentUser,
    version: str | None = Query(None, description="Version of the package"),
    platform: Platform | None = Query(None, description="Platform of the package"),
) -> list[InstallerModel]:
    result: list[InstallerModel] = []
    root = get_installer_root()
    for version_dir in os.listdir(root):
        if not os.path.isdir(os.path.join(root, version_dir)):
            continue
        if version is not None and version_dir != version:
            continue
        for p in Platform.__args__:
            if platform is not None and platform != p:
                continue
            manifest_path = os.path.join(root, version_dir, f"{p}.json")
            if not os.path.isfile(manifest_path):
                continue
            try:
                manifest = json.load(open(manifest_path, "r"))
                item = InstallerModel(**manifest)
                file_path = os.path.join(root, version_dir, item.filename)
                item.file_exists = os.path.isfile(file_path)
                if item.file_exists:
                    item.file_size = os.path.getsize(file_path)
            except Exception as e:
                logging.warning(f"Failed to load manifest file {manifest_path}: {e}")
                continue

            result.append(item)
    return result


@router.post("/installers", status_code=204)
async def create_installer(user: CurrentUser, payload: InstallerPostModel):
    if not user.is_admin:
        raise ForbiddenException("Only admins can create installers")
    installer_dir = get_version_dir(payload.version)
    manifest_path = os.path.join(installer_dir, f"{payload.platform}.json")
    with open(manifest_path, "w") as f:
        json.dump(payload.dict(), f)


@router.put("/installers/{version}/{filename}", status_code=204)
async def upload_installer_file(
    user: CurrentUser, request: Request, version: str, filename: str
):
    if not user.is_admin:
        raise ForbiddenException("Only admins can upload installers")
    manifest = get_manifest_by_filename(version, filename)
    if manifest is None:
        raise AyonException("No such installer")

    installer_dir = get_version_dir(version)
    file_path = os.path.join(installer_dir, filename)

    i = 0
    async with aiofiles.open(file_path, "wb") as f:
        async for chunk in request.stream():
            await f.write(chunk)
            i += 1

    if i == 0:
        raise AyonException("Empty file")


@router.delete("/installers/{version}", status_code=204)
async def delete_installer_version(user: CurrentUser, version: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete installers")
    version_dir = get_version_dir(version)
    if not os.path.isdir(version_dir):
        raise AyonException("No such installer")
    shutil.rmtree(version_dir)


@router.delete("/installers/{version}/{filename}", status_code=204)
async def delete_installer_file(user: CurrentUser, version: str, filename: str):
    if not user.is_admin:
        raise ForbiddenException("Only admins can delete installers")
    manifest = get_manifest_by_filename(version, filename)
    if manifest is None:
        raise AyonException("No such installer")
    version_dir = get_version_dir(version)
    file_path = os.path.join(version_dir, filename)
    if not os.path.isfile(file_path):
        raise AyonException("No such installer")
    os.remove(file_path)
    os.remove(os.path.join(version_dir, f"{manifest.platform}.json"))

    if os.listdir(version_dir) == []:
        shutil.rmtree(version_dir)


@router.get("/installers/{version}/{filename}")
async def download_installer_file(user: CurrentUser, version: str, filename: str):
    version_dir = get_version_dir(version)
    file_path = os.path.join(version_dir, filename)
    if not os.path.isfile(file_path):
        raise AyonException("No such installer")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename,
    )
